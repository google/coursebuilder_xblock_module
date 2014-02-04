# Copyright 2014 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""An XBlock to provide Capa Problem capabilities."""

__author__ = 'jorr@google.com (John Orr)'

import json
import logging
import os
import re

import appengine_config
from lxml import etree
import mako.lookup
from models import models as m_models
from models import transforms
from modules.xblock_module.xblock_module import MATHJAX_URI
import webob
import xblock.core
import xblock.fragment
import xblock.runtime
from xmodule import progress
import xmodule.capa_base


class RuntimeExtras(object):
    """A system proxy object used by the Capa questions."""

    def __init__(self, block, runtime):
        self._block = block
        self._runtime = runtime

        self.user_is_staff = False

        self.anonymous_student_id = 'anonymous_student'
        self.cache = None
        self.can_execute_unsafe_code = False
        self.DEBUG = False
        self.filestore = None
        self.node_path = None
        self.xqueue = None

    @property
    def STATIC_URL(self):
        # TODO(jorr): This abuses the local resource API because it assumes
        # all local resourcea are made by concatenation on a base (which they
        # are in the CB context, but is not guaranteed by the API).
        return self._runtime.local_resource_url(
            self._block, 'edx-platform/common/static/')

    @property
    def ajax_url(self):
        # Use the id (i.e., the usage id) for the ajax_url parameter. The
        # JavaScript library will intercept calls that use ajax_url and use
        # runtime.handler_url to compute the right url using the id.
        return self._block.id

    @property
    def seed(self):
        return self._block.seed

    def render_template(self, template_name, context):
        lookup = mako.lookup.TemplateLookup(directories=[
            'lib/edx-platform/lms/templates',
            'lib/edx-platform/common/lib/capa/capa/templates'])
        template = lookup.get_template(template_name)
        return template.render(**context)

    def track_function(self, function_name, data_dict):
        """Provide event logging."""
        logging.info(function_name, data_dict)

    def replace_course_urls(self, text):
        """Rewrite any URLs to localized form."""
        return text

    def replace_jump_to_id_urls(self, text):
        """Rewrite any URLs to localized form."""
        return text

    def replace_urls(self, text):
        """Rewrite any URLs to localized form."""
        return text


class Location(object):
    """A proxy for the Location object used by Capa questions."""

    def __init__(self, loc):
        self.loc = loc

    def html_id(self):
        return self.loc

    def url(self):
        return self.loc


def json_response(handler):

    @xblock.core.XBlock.handler
    def wrapper(self, request, unused_suffix=''):

        before = self.get_progress()

        result = handler(self, request.POST)

        after = self.get_progress()

        result.update({
            'progress_changed': after != before,
            'progress_status': progress.Progress.to_js_status_str(after),
            'progress_detail': progress.Progress.to_js_detail_str(after),
        })

        # TODO(jorr): Security - use transforms dumps
        return webob.Response(
            json.dumps(result, cls=xmodule.capa_base.ComplexEncoder),
            content_type='application/json')
    return wrapper


@xblock.core.XBlock.needs('i18n')
class ProblemBlock(xblock.core.XBlock, xmodule.capa_base.CapaMixin):

    def __init__(self, runtime, field_data, scope_ids):
        extras = RuntimeExtras(self, runtime)
        runtime = xblock.runtime.ObjectAggregator(extras, runtime)

        super(ProblemBlock, self).__init__(runtime, field_data, scope_ids)

        self.close_date = None
        self.close_date = None

        if self.seed is None:
            self.choose_new_seed()

        self.lcp = self.new_lcp(self.get_state_for_lcp())

    @property
    def id(self):
        return self.location.url()

    @property
    def location(self):
        return Location(self.scope_ids.usage_id)

    @property
    def display_name_with_default(self):
        return self.display_name or 'Problem'

    @classmethod
    def open_local_resource(cls, uri):
        if uri.startswith('public/'):
            return super(ProblemBlock, cls).open_local_resource(uri)

        if re.match(
                r'^edx-platform/common/static/'
                r'([a-zA-Z0-9\-_]+/)*[a-zA-Z0-9\-_]+\.(gif|png|js)$', uri):
            path = os.path.normpath('lib/' + uri)
            resource_file = os.path.join(appengine_config.BUNDLE_ROOT, path)
            return open(resource_file)

        if re.match(
                r'^MathJax/'
                r'([a-zA-Z0-9\-_]+/)*[a-zA-Z0-9\-_]+\.([a-zA-Z0-9]+)$', uri):
            path = os.path.normpath('lib/' + uri)
            resource_file = os.path.join(appengine_config.BUNDLE_ROOT, path)
            return open(resource_file)

        raise ValueError('Bad resource URI: %s' % uri)

    @classmethod
    def parse_xml(cls, node, runtime, keys, id_generator):
        block = runtime.construct_xblock_from_class(cls, keys)

        # Attributes become fields.
        for name, value in node.items():
            if name in block.fields:
                setattr(block, name, value)

        # The entire tree becomes the data for capa
        block.data = etree.tostring(node)

        return block

    def export_xml(self, node):
        node.tag = self.xml_element_name()

        # Set node attributes based on our fields.
        for field_name, field in self.fields.items():
            if field_name in ('children', 'parent', 'content', 'data'):
                continue
            if field.is_set_on(self):
                node.set(field_name, unicode(field.read_from(self)))

        for child in etree.fromstring(self.data):
            node.append(child)

    def student_view(self, context=None):
        prog = self.get_progress()
        context = {
            'element_id': self.location.html_id(),
            'id': self.id,
            'ajax_url': self.runtime.ajax_url,
            'progress_status': progress.Progress.to_js_status_str(prog),
            'progress_detail': progress.Progress.to_js_detail_str(prog)}
        content = self.runtime.render_template('problem_ajax.html', context)

        frag = xblock.fragment.Fragment()
        frag.add_css_url(self.runtime.local_resource_url(
            self, 'public/css/problem.css'))
        frag.add_javascript_url(
            '%s/MathJax.js?config=TeX-AMS-MML_HTMLorMML' % MATHJAX_URI)
        frag.add_javascript_url(self.runtime.local_resource_url(
            self, 'edx-platform/common/static/js/vendor/underscore-min.js'))
        frag.add_javascript_url(self.runtime.local_resource_url(
            self, 'edx-platform/common/static/coffee/javascript_loader.js'))
        frag.add_javascript_url(self.runtime.local_resource_url(
            self, 'edx-platform/common/static/coffee/capa/display.js'))
        frag.add_javascript_url(self.runtime.local_resource_url(
            self, 'public/js/problem.js'))
        frag.initialize_js('ProblemBlock')
        frag.add_content(content)
        return frag

    @json_response
    def problem_get(self, data):
        return self.get_problem(data)

    @json_response
    def problem_check(self, data):
        return self.check_problem(data)

    @json_response
    def problem_reset(self, data):
        return self.reset_problem(data)

    @json_response
    def problem_save(self, data):
        return self.save_problem(data)

    @json_response
    def problem_show(self, data):
        return self.get_answer(data)

    @json_response
    def score_update(self, data):
        return self.update_score(data)

    @json_response
    def input_ajax(self, data):
        return self.handle_input_ajax(data)

    @json_response
    def ungraded_response(self, data):
        return self.handle_ungraded_response(data)
