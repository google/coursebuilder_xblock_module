# Copyright 2013 Google Inc. All Rights Reserved.
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

"""Classes supporting creation and use of content using XBlocks.

Dependencies:
    1. XBlock (https://github.com/edx/XBlock)
    2. App Engine XBlock runtime
        (https://github.com/google/appengine_xblock_runtime)

The appropriate versions of both of these libraries must be installed the the
lib/ folder.  See README.rst for more details.
"""

__author__ = 'John Orr (jorr@google.com)'

import cgi
from cStringIO import StringIO
import logging
import mimetypes
import os
import re
import tarfile
import urllib
import uuid
from xml.etree import cElementTree

import appengine_config
from appengine_xblock_runtime import store
import appengine_xblock_runtime.runtime
from common import jinja_utils
from common import safe_dom
from common import schema_fields
from common import tags
from controllers import sites
from controllers import utils
import dbmodels
import django.conf
import django.template.loader
from lxml import etree
import messages
from models import courses
from models import custom_modules
from models import jobs
from models import transforms
import models.models as m_models
from modules.dashboard import filer
from modules.dashboard import unit_lesson_editor
import modules.dashboard.dashboard as dashboard
from modules.oeditor import oeditor
import webapp2
import workbench.runtime
import xblock.core
import xblock.exceptions
import xblock.field_data
import xblock.fields
import xblock.fragment
import xblock.plugin
import xblock.runtime

from google.appengine.ext import blobstore
from google.appengine.ext import db
from google.appengine.ext import ndb


# URI routing for resources belonging to this module
RESOURCES_URI = '/modules/xblock_module/resources'
# Base URI routing used by Course Builder for XBlock static resources
XBLOCK_RESOURCES_URI = '/modules/xblock_module/xblock_resources'
# Base URI routing used by Course Builder for XBlock static resources
XBLOCK_LOCAL_RESOURCES_URI = '/modules/xblock_module/xblock_local_resources'
# URI routing used by Course Builder for call-backs to server-side XBlock code
HANDLER_URI = '/modules/xblock_module/handler'
# URI routing the the MathJax package
MATHJAX_URI = '/modules/xblock_module/MathJax'

# Allow images of up to 5Mb
MAX_ASSET_UPLOAD_SIZE_K = 5 * 1024

# The location of the static workbench files used by the XBlocks
WORKBENCH_STATIC_PATH = os.path.normpath('lib/XBlock/workbench/static')
# The location of the DJango templates used by XBlocks
XBLOCK_TEMPLATES_PATH = 'lib/XBlock/xblock/templates'
# XSRF protection token for handler callbacks
XBLOCK_XSRF_TOKEN_NAME = 'xblock_handler'

XBLOCK_EVENT_SOURCE_NAME = 'xblock-event'

XBLOCK_WHITELIST = [
    'sequential = cb_xblocks_core.cb_xblocks_core:SequenceBlock',
    'video = cb_xblocks_core.cb_xblocks_core:VideoBlock',
    'cbquestion = cb_xblocks_core.cb_xblocks_core:QuestionBlock',
    'html = cb_xblocks_core.cb_xblocks_core:HtmlBlock',
    'vertical = cb_xblocks_core.cb_xblocks_core:VerticalBlock',
    'problem = cb_xblocks_core.problem:ProblemBlock'
]

# XBlock runtime section


class StudentFieldData(xblock.field_data.SplitFieldData):
    """A field data manager for use in student (i.e., non-admin) context.

    This field data manager prevents students from modifying a field which is
    stored as UserScope.NONE, even if an XBlock includes code which sets it.
    Thus it defends against poorly-written XBlocks which grant students too
    wide permissions.
    """

    def __init__(self, db_data):

        authored_data = xblock.field_data.ReadOnlyFieldData(db_data)
        student_data = db_data

        super(StudentFieldData, self).__init__({
            xblock.fields.Scope.content: authored_data,
            xblock.fields.Scope.settings: authored_data,
            xblock.fields.Scope.parent: authored_data,
            xblock.fields.Scope.children: authored_data,
            xblock.fields.Scope.user_state_summary: student_data,
            xblock.fields.Scope.user_state: student_data,
            xblock.fields.Scope.user_info: student_data,
            xblock.fields.Scope.preferences: student_data})


class ForbiddenXBlockError(Exception):
    """Raised when a non-whitelisted XBlock is requested."""


def select_xblock(identifier, entry_points):
    """Hook called when loading XBlock classes, which enforces whitelist."""
    entry_point = xblock.plugin.default_select(identifier, entry_points)
    if str(entry_point) not in XBLOCK_WHITELIST:
        raise ForbiddenXBlockError(
            'Attempted to load forbidden XBlock: %s' % str(entry_point))
    return entry_point


class MemoryIdManager(xblock.runtime.MemoryIdManager):

    def create_usage(self, def_id, usage_id=None):
        """Extend the method definition to allow a specified usage_id."""
        usage_id = usage_id or appengine_xblock_runtime.runtime.generate_id()
        self._usages[usage_id] = def_id
        return usage_id

    def create_definition(self, block_type, def_id=None):
        """Extend the method definition to allow a specified def_id."""
        def_id = def_id or appengine_xblock_runtime.runtime.generate_id()
        self._definitions[def_id] = block_type
        return def_id


class Runtime(appengine_xblock_runtime.runtime.Runtime):
    """A XBlock runtime which uses the App Engine datastore."""

    def __init__(
            self, handler, id_reader=None, field_data=None, student_id=None,
            is_admin=False):

        field_data = field_data or xblock.runtime.KvsFieldData(
            store.KeyValueStore())

        if is_admin:
            pass
        elif student_id:
            field_data = StudentFieldData(field_data)
        else:
            field_data = xblock.field_data.ReadOnlyFieldData(field_data)

        def get_jinja_template(template_name, dirs):
            locale = handler.app_context.get_environ()['course']['locale']
            return jinja_utils.get_template(template_name, dirs, locale=locale)
        services = {'jinja': get_jinja_template}

        super(Runtime, self).__init__(
            id_reader=id_reader, field_data=field_data, student_id=student_id,
            services=services, select=select_xblock)
        self.handler = handler

    def render_template(self, template_name, **kwargs):
        """Loads the django template for `template_name."""
        template = django.template.loader.get_template(template_name)
        return template.render(django.template.Context(kwargs))

    def wrap_child(self, block, unused_view, frag, unused_context):
        wrapped = xblock.fragment.Fragment()
        wrapped.add_javascript_url(
            self.resource_url('js/vendor/jquery.min.js'))
        wrapped.add_javascript_url(
            self.resource_url('js/vendor/jquery.cookie.js'))

        data = {}
        if frag.js_init_fn:

            # Patch to accommodate jqueryui tabs (used by sequence XBlock)in a
            # page with <base> tag set. See:
            #   http://stackoverflow.com/questions/13837304/jquery-ui-non-ajax-tab-loading-whole-website-into-itself
            wrapped.add_javascript("""
                $(function() {
                  $(".xblock .tabs ul li a").each(function() {
                    var href = $(this).attr("href");
                    if (href && href.charAt(0) == "#") {
                      $(this).attr("href", location.href.toString() + href);
                    }
                  });
                });
                """)

            wrapped.add_javascript_url(
                self.resource_url('js/runtime/%s.js' % frag.js_init_version))
            wrapped.add_javascript_url(RESOURCES_URI + '/runtime.js')
            data = {
                'data-init': frag.js_init_fn,
                'data-runtime-version': str(frag.js_init_version),
                'data-usage': block.scope_ids.usage_id,
                'data-block-type': block.scope_ids.block_type,
                'data-xsrf-token': utils.XsrfTokenManager.create_xsrf_token(
                    XBLOCK_XSRF_TOKEN_NAME)}

        if block.name:
            data['data-name'] = block.name

        class FragmentText(safe_dom.Text):
            """Class to insert the fragment content into the safe_dom node."""

            def __init__(self, value):
                self._value = unicode(value)

            @property
            def sanitized(self):
                return self._value

        div = safe_dom.Element('div', className='xblock', **data)
        div.add_child(FragmentText(frag.body_html()))

        wrapped.add_content(unicode(div))
        wrapped.add_frag_resources(frag)
        return wrapped

    def _usage_id_from_node(self, node, parent_id, _id_generator):
        """Override import method from XBlock runtime."""
        block_type = node.tag
        usage_id = node.get('usage_id')

        if usage_id is None:
            # In Course Builder the usages and defs are in 1-1
            # correspondence so for definiteness, make id's the same
            def_id = _id_generator.create_definition(block_type)
            usage_id = _id_generator.create_usage(def_id, usage_id=def_id)
        else:
            # Test whether or not the usage is already in the datastore. If it
            # is not present, there will be a NoSuchUsage exception.
            try:
                def_id = self.id_reader.get_definition_id(usage_id)
            except xblock.exceptions.NoSuchUsage:
                # In Course Builder the usages and defs are in 1-1
                # correspondence so for definiteness, make id's the same
                def_id = usage_id
                def_id = _id_generator.create_definition(
                    block_type, def_id=def_id)
                _id_generator.create_usage(def_id, usage_id=usage_id)

        keys = xblock.fields.ScopeIds(
            xblock.fields.UserScope.NONE, block_type, def_id, usage_id)
        block_class = self.mixologist.mix(self.load_block_type(block_type))

        # Load the block's fields and clear out any existing children
        block = self.construct_xblock_from_class(block_class, keys)
        if hasattr(block, 'children'):
            # We need to force an explict save of the 'children' field
            # and so first we have to make it dirty
            block.children = ['dirt']
            block.save()
            block.children = []
            block.save()

        # Reload the block and attach new children
        block = block_class.parse_xml(node, self, keys, _id_generator)
        block.parent = parent_id
        block.save()
        return usage_id

    def export_to_xml(self, block, xmlfile):
        """Override export method from XBlock runtime."""
        root = etree.Element('unknown_root', usage_id=block.scope_ids.usage_id)
        tree = etree.ElementTree(root)
        block.export_xml(root)
        tree.write(
            xmlfile, xml_declaration=True, encoding='utf8', pretty_print=True)

    def add_block_as_child_node(self, block, node):
        """Override export method from XBlock runtime."""
        child = etree.SubElement(
            node, 'unknown', usage_id=block.scope_ids.usage_id)
        block.export_xml(child)

    def query(self, block):
        # pylint: disable=protected-access
        return workbench.runtime._BlockSet(self, [block])
        # pylint: enable=protected-access

    def handler_url(self, block, handler_name, suffix='', query=''):
        return self.handler.canonicalize_url('%s?%s' % (
            HANDLER_URI, urllib.urlencode({
                'usage': block.scope_ids.usage_id,
                'handler': handler_name,
                'xsrf_token': utils.XsrfTokenManager.create_xsrf_token(
                    XBLOCK_XSRF_TOKEN_NAME)})))

    def resource_url(self, resource):
        return '%s/%s' % (XBLOCK_RESOURCES_URI, resource)

    def local_resource_url(self, block, uri):
        return '%s/%s/%s' % (
            XBLOCK_LOCAL_RESOURCES_URI, block.scope_ids.block_type, uri)

    def publish(self, block, event):
        if self.user_id is None:
            return

        wrapper = {
            'usage': block.scope_ids.usage_id,
            'type': block.scope_ids.block_type,
            'event': event}

        m_models.EventEntity(
            source=XBLOCK_EVENT_SOURCE_NAME,
            user_id=self.user_id,
            data=transforms.dumps(wrapper)).put()

    def parse_xml_string(
            self, xml_str, unused_id_generator, orig_xml_str=None,
            dry_run=False, log=None):
        """Override parse_xml_string to make it asynchronous.

        Calls to this method will execute using NDB's asynchronous API. In order
        to ensure all the Datastore RPC's terminate successfully, it is
        essential that some method higher up the call stack (e.g., the request
        handler) should be decorated with @ndb.toplevel.

        Args:
            xml_str: str. The string of XML which will be parsed as XBlocks.
            unused_id_generator: IdGenerator. The XBlock API allows the runtime
                to use different usage- and definition-generators, but in this
                implementation, the only write target is the App Engine
                Datastore.
            orig_xml_str: str. The XML representation of the existing block in
                the datastore, if it exists.
            dry_run: bool. If set True, then parse the XML but do not do any
                datastore writes.
            log: file-like. A buffer to write back the XML representation of the
                XBlock tree which has been assembled.

        Returns:
            str. The usage id of the root block of the XML tree.
        """
        if orig_xml_str is None:
            orig_xml_str = ''
        if log is None:
            log = StringIO()

        id_manager = MemoryIdManager()
        dict_key_value_store = xblock.runtime.DictKeyValueStore()

        old_id_reader = self.id_reader
        self.id_reader = id_manager

        old_field_data = self.field_data
        self.field_data = xblock.runtime.KvsFieldData(dict_key_value_store)

        try:
            root_usage_id = super(Runtime, self).parse_xml_string(
                xml_str, id_manager)

            block = self.get_block(root_usage_id)
            self.export_to_xml(block, log)
        finally:
            self.id_reader = old_id_reader
            self.field_data = old_field_data

        if dry_run or log.getvalue() == orig_xml_str:
            return root_usage_id

        entities = []
        for key, value in dict_key_value_store.db_dict.iteritems():
            ndb_key = ndb.Key(store.KeyValueEntity, store.key_string(key))
            kv_entity = store.KeyValueEntity(key=ndb_key)
            kv_entity.value = value
            entities.append(kv_entity)

        for def_id, block_type in id_manager._definitions.iteritems():
            ndb_key = ndb.Key(store.DefinitionEntity, def_id)
            def_entity = store.DefinitionEntity(key=ndb_key)
            def_entity.block_type = block_type
            entities.append(def_entity)

        for usage_id, def_id in id_manager._usages.iteritems():
            ndb_key = ndb.Key(store.UsageEntity, usage_id)
            usage_entity = store.UsageEntity(key=ndb_key)
            usage_entity.definition_id = def_id
            entities.append(usage_entity)

        ndb.put_multi_async(entities)

        return root_usage_id


class XBlockActionHandler(utils.BaseHandler):

    def _handle_request(self):
        def fix_ajax_request_body(body):
            # The XBlock ajax clients send JSON strings in the POST body, but if
            # the content-type is not explicitly set to application/json then
            # the handler receives name=value pairs in url-encoded
            # strings.
            return urllib.unquote(
                body[:-1]) if body and body[-1] == '=' else body

        if self.get_user() is not None:
            student_id = self.get_user().user_id()
        else:
            student_id = get_session_id_for_guest_user(self)

        token = self.request.get('xsrf_token')
        if not utils.XsrfTokenManager.is_xsrf_token_valid(
                token, XBLOCK_XSRF_TOKEN_NAME):
            self.error(400)
            return

        usage_id = self.request.get('usage')
        handler_name = self.request.get('handler')

        rt = Runtime(self, student_id=student_id)
        block = rt.get_block(usage_id)
        self.request.body = fix_ajax_request_body(self.request.body)
        response = block.runtime.handle(block, handler_name, self.request)
        self.response.body = response.body
        self.response.headers.update(response.headers)

    def get(self):
        self._handle_request()

    def post(self):
        self._handle_request()


# Data model section


class RootUsageEntity(m_models.BaseEntity):
    """Datastore entiry for root usage objects.

    Application code should not access this object direct. Use RootUsageDto
    and RootUsageDao instead.
    """
    data = db.TextProperty(indexed=False)


class RootUsageDto(object):
    """A root usage identifies the root of a tree of XBlocks.

    Application code should use this data transfer object (DTO) class and the
    associated DAO to interact with the datastore.
    """

    def __init__(self, the_id, the_dict):
        self.id = the_id
        self.dict = the_dict

    @property
    def description(self):
        return self.dict.get('description', '')

    @property
    def usage_id(self):
        return self.dict.get('usage_id', '')

    @property
    def is_imported(self):
        """Whether the usage was created as an import of an archive file.

        Imported root usage entities are wiped and re-inserted when a new
        archive is merged in; non-imported entities are left alone.

        Returns:
            bool. Whether the usage was created as part of an import.
        """
        return self.dict.get('is_imported', False)


class RootUsageDao(m_models.BaseJsonDao):
    """DAO for CRUD operations on root usage objects."""
    DTO = RootUsageDto
    ENTITY = RootUsageEntity


# XBlock editor section

EDITOR_HANDLERS = ['add_xblock', 'edit_xblock', 'import_xblock']


_orig_get_template = dashboard.DashboardHandler.get_template


def _get_template(the_dashboard, template_name, dirs):
    return _orig_get_template(
        the_dashboard, template_name, dirs + [os.path.join(
            appengine_config.BUNDLE_ROOT, 'modules', 'xblock_module')])


def _add_editor_to_dashboard():
    for handler in EDITOR_HANDLERS:
        dashboard.DashboardHandler.get_actions.append(handler)
        setattr(
            dashboard.DashboardHandler, 'get_%s' % handler,
            globals()['_get_%s' % handler])

    setattr(dashboard.DashboardHandler, 'get_template', _get_template)

    dashboard.DashboardHandler.contrib_asset_listers.append(list_xblocks)
    dashboard.DashboardHandler.child_routes.append(
        [XBlockEditorRESTHandler.URI, XBlockEditorRESTHandler])
    dashboard.DashboardHandler.child_routes.append(
        [XBlockArchiveRESTHandler.URI, XBlockArchiveRESTHandler])
    dashboard.DashboardHandler.child_routes.append(
        [XBlockArchiveProgressQueryHandler.URI, XBlockArchiveProgressQueryHandler])


def _remove_editor_from_dashboard():
    for handler in EDITOR_HANDLERS:
        dashboard.DashboardHandler.get_actions.remove(handler)
        delattr(dashboard.DashboardHandler, 'get_%s' % handler)

    setattr(dashboard.DashboardHandler, 'get_template', _orig_get_template)

    dashboard.DashboardHandler.contrib_asset_listers.remove(list_xblocks)
    dashboard.DashboardHandler.child_routes.remove(
        [XBlockEditorRESTHandler.URI, XBlockEditorRESTHandler])
    dashboard.DashboardHandler.child_routes.remove(
        [XBlockArchiveRESTHandler.URI, XBlockArchiveRESTHandler])
    dashboard.DashboardHandler.child_routes.remove(
        [XBlockArchiveProgressQueryHandler.URI, XBlockArchiveProgressQueryHandler])


def list_xblocks(the_dashboard):
    """Prepare a list of the root XBlock usages installed."""
    if not filer.is_editable_fs(the_dashboard.app_context):
        return safe_dom.NodeList()

    output = safe_dom.NodeList()

    import_button_text = 'Import'
    if courses.Course(the_dashboard).get_units():
        import_button_text = 'Merge'
    output.append(
        safe_dom.Element(
            'a', className='gcb-button gcb-pull-right',
            href='dashboard?action=import_xblock'
        ).add_text(import_button_text)
    )

    output.append(
        safe_dom.Element(
            'a', className='gcb-button gcb-pull-right',
            href='dashboard?action=add_xblock'
        ).add_text('Add XBlock')
    ).append(
        safe_dom.Element('div', style='clear: both; padding-top: 2px;')
    ).append(safe_dom.Element('h3').add_text('XBlocks'))

    root_usages = sorted(
        RootUsageDao.get_all(), key=lambda x: x.description.lower())

    if root_usages:
        ol = safe_dom.Element('ol')
        for root_usage in root_usages:
            edit_url = 'dashboard?action=edit_xblock&key=%s' % root_usage.id
            li = safe_dom.Element('li')
            li.add_text(root_usage.description).add_child(
                safe_dom.Entity('&nbsp;')
            ).add_child(
                safe_dom.Element('a', href=edit_url).add_text('[Edit]'))
            ol.add_child(li)
        output.append(ol)
    else:
        output.append(safe_dom.Element('blockquote').add_text('< none >'))
    return output


def _render_editor(the_dashboard, key=None, title=None, description=None):
    key = key or ''
    rest_url = the_dashboard.canonicalize_url(XBlockEditorRESTHandler.URI)
    exit_url = the_dashboard.canonicalize_url('/dashboard?action=assets')

    delete_url = None
    if key:
        delete_url = '%s?%s' % (
            the_dashboard.canonicalize_url(XBlockEditorRESTHandler.URI),
            urllib.urlencode({
                'key': key,
                'xsrf_token': cgi.escape(the_dashboard.create_xsrf_token(
                    XBlockEditorRESTHandler.XSRF_TOKEN))}))
    main_content = oeditor.ObjectEditor.get_html_for(
        the_dashboard,
        XBlockEditorRESTHandler.SCHEMA.get_json_schema(),
        XBlockEditorRESTHandler.SCHEMA.get_schema_dict(),
        key, rest_url, exit_url,
        delete_url=delete_url, delete_method='delete',
        required_modules=XBlockEditorRESTHandler.REQUIRED_MODULES)
    template_values = {
        'page_title': the_dashboard.format_title(title),
        'page_title_linked': the_dashboard.format_title(title, as_link=True),
        'page_description': description,
        'main_content': main_content}
    the_dashboard.render_page(template_values)


def _get_add_xblock(the_dashboard):
    _render_editor(
        the_dashboard, title=messages.ADD_XBLOCK_TITLE,
        description=messages.ADD_XBLOCK_DESCRIPTION)


def _get_edit_xblock(the_dashboard):
    _render_editor(
        the_dashboard, key=the_dashboard.request.get('key'),
        title=messages.EDIT_XBLOCK_TITLE,
        description=messages.EDIT_XBLOCK_DESCRIPTION)


def _get_import_xblock(the_dashboard):
    """Render the screen for uploading an XBlock course tar.gx file."""
    rest_url = the_dashboard.canonicalize_url(XBlockArchiveRESTHandler.URI)
    exit_url = the_dashboard.canonicalize_url('/dashboard?action=assets')
    extra_js_files = []

    extra_js_files.append('resources/import.js')
    if courses.Course(the_dashboard).get_units():
        extra_js_files.append('resources/merge.js')

    main_content = oeditor.ObjectEditor.get_html_for(
        the_dashboard,
        XBlockArchiveRESTHandler.SCHEMA.get_json_schema(),
        XBlockArchiveRESTHandler.SCHEMA.get_schema_dict(),
        None, rest_url, exit_url,
        delete_url=None,
        auto_return=False,
        save_method='upload',
        save_button_caption='Import',
        required_modules=XBlockArchiveRESTHandler.REQUIRED_MODULES,
        extra_css_files=['resources/import.css'],
        extra_js_files=extra_js_files)
    template_values = {
        'page_title': messages.IMPORT_COURSE_PAGE_TITLE,
        'page_description': messages.IMPORT_COURSE_PAGE_DESCRIPTION,
        'main_content': main_content}
    the_dashboard.render_page(template_values)


class XBlockEditorRESTHandler(utils.BaseRESTHandler):
    URI = '/rest/xblock'

    SCHEMA = schema_fields.FieldRegistry('XBlock', description='XBlock XML')
    SCHEMA.add_property(
        schema_fields.SchemaField('xml', 'XML', 'text', optional=True))
    SCHEMA.add_property(
        schema_fields.SchemaField(
            'description', 'Description', 'string', optional=True,
            description=messages.XBLOCK_DESCRIPTION_FIELD))

    REQUIRED_MODULES = []

    XSRF_TOKEN = 'xblock-edit'

    def get(self):
        key = self.request.get('key')

        if not unit_lesson_editor.CourseOutlineRights.can_view(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        payload_dict = {'xml': '', 'description': ''}
        if key:
            root_usage = RootUsageDao.load(key)
            rt = Runtime(self, is_admin=True)
            block = rt.get_block(root_usage.usage_id)
            xml_buffer = StringIO()
            rt.export_to_xml(block, xml_buffer)
            payload_dict = {
                'xml': xml_buffer.getvalue(),
                'description': root_usage.description}

        transforms.send_json_response(
            self, 200, 'Success',
            payload_dict=payload_dict,
            xsrf_token=utils.XsrfTokenManager.create_xsrf_token(
                self.XSRF_TOKEN))

    def import_and_validate(self, key, unvalidated_dict):
        errors = []
        try:
            validated_dict = transforms.json_to_dict(
                unvalidated_dict, self.SCHEMA.get_json_schema_dict())
        except ValueError as err:
            errors.append(str(err))
            return (None, errors)

        if not validated_dict.get('description'):
            errors.append('Missing description field')

        descriptions = {
            root.description for root in RootUsageDao.get_all()
            if not key or root.id != long(key)}
        if validated_dict['description'] in descriptions:
            errors.append(
                'The description must be different from existing XBlocks.')

        if not validated_dict.get('xml'):
            errors.append('Missing XML data')

        return validated_dict, errors

    @ndb.toplevel
    def put(self):
        request = transforms.loads(self.request.get('request'))
        key = request.get('key') or None

        if not self.assert_xsrf_token_or_fail(
                request, self.XSRF_TOKEN, {'key': key}):
            return

        if not unit_lesson_editor.CourseOutlineRights.can_edit(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        payload, errors = self.import_and_validate(
            key, transforms.loads(request.get('payload')))
        if errors:
            self.validation_error('\n'.join(errors), key=key)
            return

        try:
            rt = Runtime(self, is_admin=True)
            usage_id = rt.parse_xml_string(
                unicode(payload['xml']).encode('utf_8'), None)
        except Exception as e:  # pylint: disable=broad-except
            transforms.send_json_response(self, 412, str(e))
            return

        root_usage = RootUsageDto(
            key, {'description': payload['description'], 'usage_id': usage_id})
        key = RootUsageDao.save(root_usage)

        transforms.send_json_response(
            self, 200, 'Saved.', payload_dict={'key': key})

    def delete(self):
        key = self.request.get('key')

        if not self.assert_xsrf_token_or_fail(
                self.request, self.XSRF_TOKEN, {'key': key}):
            return

        if not unit_lesson_editor.CourseOutlineRights.can_edit(self):
            transforms.send_json_response(
                self, 401, 'Access denied.', {'key': key})
            return

        # TODO(jorr): Remove the tree from the UsageStore?
        RootUsageDao.delete(RootUsageDto(key, {}))
        transforms.send_json_response(self, 200, 'Deleted.')


class XBlockArchiveRESTHandler(utils.BaseRESTHandler):
    """Provide the REST API for importing XBlock archives."""

    URI = '/rest/xblock_archive'

    SCHEMA = schema_fields.FieldRegistry('XBlock', description='XBlock XML')
    SCHEMA.add_property(
        schema_fields.SchemaField(
            'file', 'File', 'string', optional=True,
            description=messages.XBLOCK_ARCHIVE_FIELD,
            extra_schema_dict_values={'_type': 'file'}))
    SCHEMA.add_property(
        schema_fields.SchemaField(
            'dry_run', 'Dry Run', 'boolean', optional=True,
            description=messages.XBLOCK_ARCHIVE_DRY_RUN))

    REQUIRED_MODULES = ['inputex-file', 'io-upload-iframe', 'inputex-checkbox']

    XSRF_TOKEN = 'xblock-import'

    def get(self):
        """Provide empty inital content for import editor."""
        transforms.send_json_response(
            self, 200, 'Success',
            payload_dict={
                'file': '',
                'upload_url': blobstore.create_upload_url(
                    self.canonicalize_url(self.URI)),
                'poller_url': self.canonicalize_url(
                    XBlockArchiveProgressQueryHandler.URI)
            },
            xsrf_token=utils.XsrfTokenManager.create_xsrf_token(
                self.XSRF_TOKEN))

    def post(self):
        assert courses.is_editable_fs(self.app_context)

        request = transforms.loads(self.request.get('request'))
        if not self.assert_xsrf_token_or_fail(
                request, self.XSRF_TOKEN, {'key': ''}):
            return

        if (not unit_lesson_editor.CourseOutlineRights.can_edit(self) or
            not filer.FilesRights.can_add(self)):

            transforms.send_file_upload_response(
                self, 401, 'Access denied.')
            return

        try:
            payload = transforms.json_to_dict(
                transforms.loads(request.get('payload')),
                self.SCHEMA.get_json_schema_dict())
        except ValueError as err:
            transforms.send_file_upload_response(self, 412, str(err))
            return

        dry_run = payload.get('dry_run', False)

        upload = self.request.POST['file']

        if not isinstance(upload, cgi.FieldStorage):
            transforms.send_file_upload_response(
                self, 403, 'No file specified.')
            return

        blob_key = blobstore.parse_blob_info(upload).key()
        XBlockArchiveJob(
            self.app_context, blob_key=blob_key, dry_run=dry_run).submit()

        # Pass a new upload url back to the page for future uploads
        new_upload_url = blobstore.create_upload_url(
            self.canonicalize_url(self.URI))

        transforms.send_file_upload_response(
            self, 200, 'Processing upload...',
            payload_dict={'new_upload_url': new_upload_url})


class XBlockArchiveJob(jobs.DurableJob):
    """The offline job which handles installing an uploaded archive file."""

    def __init__(self, app_context, blob_key=None, dry_run=True):
        super(XBlockArchiveJob, self).__init__(app_context)
        self.app_context = app_context
        self.blob_key = blob_key
        self.dry_run = dry_run

    @ndb.toplevel
    def run(self):
        def status(success_flag, message):
            return {
                'success': success_flag,
                'message': message}

        blob_info = blobstore.BlobInfo.get(self.blob_key)
        try:
            fileobj = blobstore.BlobReader(
                self.blob_key, buffer_size=1024 * 1024)
            archive = tarfile.open(fileobj=fileobj, mode='r:gz')
        except Exception as e:  # pylint: disable=broad-except
            return status(False, 'Unable to read the archive file: %s' % e)

        try:
            course = courses.Course(None, app_context=self.app_context)
            rt = Runtime(self, is_admin=True)
            journal = []
            importer = Importer(
                archive=archive, course=course, fs=self.app_context.fs.impl,
                rt=rt, dry_run=self.dry_run, journal=journal)
            importer.parse()

            validation_errors = importer.validate()
            if validation_errors:
                return status(
                    False, 'Import failed: %s' % '\n'.join(validation_errors))

            importer.do_import()

            if self.dry_run:
                return status(
                    True,
                    'Upload successfully validated:\n%s' % '\n'.join(journal))

            course.save()

        except Exception as e:  # pylint: disable=broad-except
            logging.exception('Import failed')
            return status(False, 'Import failed: %s' % e)
        finally:
            archive.close()

        return status(
            True, 'Upload successfully imported:\n%s' % '\n'.join(journal))


class XBlockArchiveProgressQueryHandler(utils.BaseRESTHandler):
    """A handler to respond to Ajax polling on the progress of the import."""

    URI = '/rest/xblock_archive_progress'

    def get(self):
        job = XBlockArchiveJob(self.app_context)
        if job.is_active():
            payload_dict = {'complete': False}
        else:
            payload_dict = {
                'complete': True,
                'output': job.load().output}

        transforms.send_json_response(
            self, 200, 'Polling', payload_dict=payload_dict)


class BadImportException(Exception):
    """Exception raised when in Importer."""
    pass


class Differ(object):
    """Base class for tracking the difference between two lists of objects.

    The types of object in the two lists need not be the same, and so subclasses
    must implements methods which extract an 'id' from members of the 'old list'
    and the 'new list'. The result will be three classes:

      unbound: the set of objects in the old list whioch have no ids.
      bindings: a dict of mappings of ids from the new list to objects with the
          same id in the old list.
      orphans: the set of objects in the old list which have ids but are do not
          correspond to the ids of any elements in the new list.
    """

    def __init__(self, new_objects, old_objects):
        self.unbound = set()
        self._new_ids = set()
        self.bindings = {}
        self.orphans = set()

        for new in new_objects:
            _id = self.get_new_id(new)
            assert _id
            self._new_ids.add(_id)

        for old in old_objects:
            _id = self.get_old_id(old)
            if not _id:
                self.unbound.add(old)
            elif _id in self._new_ids:
                self.bindings[_id] = old
            else:
                self.orphans.add(old)

    def get_new_id(self, new):
        raise NotImplementedError()

    def get_old_id(self, old):
        raise NotImplementedError()

    def bind(self, new, old):
        raise NotImplementedError()


class Sequential2LessonMapper(Differ):
    """A class that handles mapping sequentials to lessons."""

    def __init__(self, importer, chapter, unit):
        super(Sequential2LessonMapper, self).__init__(
            chapter, importer.course.get_lessons(unit.unit_id))

    def get_new_id(self, sequential):
        return sequential.attrib['usage_id']

    def get_old_id(self, lesson):
        return lesson.properties.get('xblock.usage_id')

    def bind(self, sequential, lesson):
        lesson.properties['xblock.usage_id'] = sequential.attrib['usage_id']


class Chapter2UnitMapper(Differ):
    """A class that handles mapping chapters to units."""

    def __init__(self, importer):
        super(Chapter2UnitMapper, self).__init__(
            importer.course_root, importer.course.get_units())

    def get_new_id(self, chapter):
        return chapter.attrib['usage_id']

    def get_old_id(self, unit):
        return unit.properties.get('xblock.usage_id')

    def bind(self, chapter, unit):
        unit.properties['xblock.usage_id'] = chapter.attrib['usage_id']


class Importer(object):
    """Manages the import of an XBlock archive file."""

    def __init__(
            self, archive=None, course=None, fs=None, rt=None, dry_run=False,
            journal=None):
        self.archive = archive
        self.course = course
        self.fs = fs
        self.rt = rt
        self.dry_run = dry_run
        self.base = self._get_base_folder_name()
        self.course_root = None
        self.journal = journal if journal is not None else []

    def parse(self):
        """Assemble the XML files in the archive into a single DOM."""
        course_file = self.archive.extractfile('%s/course.xml' % self.base)
        self.course_root = self._walk_tree(
            cElementTree.parse(course_file).getroot())

    def validate(self):
        """Check that the course structure is compatible with CB."""
        errors = []

        # the root must be a course
        if self.course_root.tag != 'course':
            errors.append('There is no root course tag.')

        # The immediate children must be chapters
        for child in self.course_root:
            if child.tag != 'chapter':
                errors.append('All content must be in chapters.')
                break
            # The grandchildren must be sequentials
            for grandchild in child:
                if grandchild.tag != 'sequential':
                    errors.append('Chapters may only contain sequentials.')
                    break

        return errors

    def _update_unit(self, chapter, unit):
        new_title = chapter.attrib['display_name']
        old_title = unit.title
        unit.title = new_title
        self.journal.append('Update unit title from \'%s\' to \'%s\'' % (
            old_title, new_title))

    def _create_unit(self, chapter):
        assert chapter.tag == 'chapter'
        unit = self.course.add_unit()
        unit.title = chapter.attrib['display_name']
        self.journal.append('Create unit \'%s\'' % unit.title)
        return unit

    def _update_lesson(self, sequential, lesson):
        new_title = sequential.attrib['display_name']
        old_title = lesson.title
        lesson.title = new_title
        self.journal.append('Update lesson title from \'%s\' to \'%s\'' % (
            old_title, new_title))

    def _create_lesson(self, sequential, unit):
        assert sequential.tag == 'sequential'
        lesson = self.course.add_lesson(unit)
        lesson.title = sequential.attrib['display_name']
        self.journal.append('Create lesson \'%s\'' % lesson.title)
        return lesson

    def _update_lesson_xblock_content(self, sequential, unit, lesson):
        xml_buffer = StringIO()
        cElementTree.ElementTree(element=sequential).write(xml_buffer)

        orig_xml_buff = StringIO()
        new_xml_buff = StringIO()

        # Get the original XML repr of this sequential for comparison
        usage_id = sequential.attrib['usage_id']
        try:
            orig_xml = self.rt.get_block(usage_id)
            self.rt.export_to_xml(orig_xml, orig_xml_buff)
        except xblock.exceptions.NoSuchUsage:
            pass  # Buffer will be empty

        usage_id = self.rt.parse_xml_string(
            xml_buffer.getvalue(), None, orig_xml_str=orig_xml_buff.getvalue(),
            dry_run=self.dry_run, log=new_xml_buff)

        # Journal the effect of the update
        if orig_xml_buff.getvalue() == new_xml_buff.getvalue():
            action = 'unchanged'
        elif not orig_xml_buff.getvalue():
            action = 'inserted'
        else:
            action = 'updated'

        self.journal.append(
            'XBlock content %(action)s in \'%(title)s\' (%(id)s)' % {
                'action': action, 'title': lesson.title, 'id': usage_id})

        # Insert a RootUsageEntity to link the lesson to the XBlock
        description = 'Unit %s, Lesson %s: %s' % (
            unit.index, lesson.index, lesson.title)
        root_usage = RootUsageDto(
            None, {
                'description': description,
                'usage_id': usage_id,
                'is_imported': True})
        root_id = RootUsageDao.save(root_usage) if not self.dry_run else 'xxx'

        # insert the xblock asset into lesson content
        lesson.objectives = '<xblock root_id="%s"></xblock>' % root_id

    def _delete_all_imported_root_usage_dtos(self):
        dao = RootUsageDao()
        for dto in RootUsageDao.get_all():
            if dto.is_imported:
                dao.delete(dto)

    def do_import(self):
        """Perform the import and create resources in CB."""
        finalize_writes_callback = self._import_static_files()

        if not self.dry_run:
            self._delete_all_imported_root_usage_dtos()

        cu_mapper = Chapter2UnitMapper(self)
        for chapter in self.course_root:
            chapter_usage_id = chapter.attrib['usage_id']
            unit = cu_mapper.bindings.get(chapter_usage_id)
            if unit:
                self._update_unit(chapter, unit)
            else:
                unit = self._create_unit(chapter)

            cu_mapper.bind(chapter, unit)

            sl_mapper = Sequential2LessonMapper(self, chapter, unit)
            for sequential in chapter:
                sequential_usage_id = sequential.attrib['usage_id']
                lesson = sl_mapper.bindings.get(sequential_usage_id)
                if lesson:
                    self._update_lesson(sequential, lesson)
                else:
                    lesson = self._create_lesson(sequential, unit)

                sl_mapper.bind(sequential, lesson)
                self._update_lesson_xblock_content(sequential, unit, lesson)

            for lesson in sl_mapper.orphans:
                self.journal.append('Delete lesson \'%s\'' % lesson.title)
                self.course.delete_lesson(lesson)

        for unit in cu_mapper.orphans:
            self.journal.append('Delete unit \'%s\'' % unit.title)
            self.course.delete_unit(unit)

        # Wait for async db operations to complete
        finalize_writes_callback()

    def _get_base_folder_name(self):
        for member in self.archive.getmembers():
            if member.isdir() and '/' not in member.name:
                return member.name
        return None

    def _walk_tree(self, node):
        if 'url_name' in node.attrib:
            # If the node refers to another file. open it and merge it in
            target_path = '%s/%s/%s.xml' % (
                self.base, node.tag, node.attrib['url_name'])
            target_file = self.archive.extractfile(target_path)
            sub_tree = self._walk_tree(
                cElementTree.parse(target_file).getroot())
            sub_tree.attrib['usage_id'] = node.attrib['url_name']
            return sub_tree
        elif node.tag == 'html':
            if 'filename' in node.attrib:
                # If the node is an <html/> block with externalized content,
                # read it in.
                target_path = '%s/html/%s.html' % (
                    self.base, node.attrib['filename'])
                target_file = self.archive.extractfile(target_path)
                node.append(tags.html_string_to_element_tree(
                    target_file.read().decode('utf8')))
                del node.attrib['filename']
            self._rebase_html_refs(node)
            return node
        else:
            for index, child in enumerate(node):
                new_child = self._walk_tree(child)
                node.remove(child)
                node.insert(index, new_child)
            return node

    def _rebase_html_refs(self, node):
        """Rebase HTML references based on /static to use CB namespace."""
        for attr in ['href', 'src']:
            if node.attrib.get(attr, '').startswith('/static/'):
                node.attrib[attr] = 'assets/img%s' % node.attrib[attr]
        for child in node:
            self._rebase_html_refs(child)

    def _import_static_files(self):
        filedata_list = []
        for member in self.archive.getmembers():
            if member.isfile() and member.name.startswith(
                    '%s/static/' % self.base):
                self._insert_filedata(filedata_list, member)

        return self.fs.put_multi_async(filedata_list)

    def _insert_filedata(self, filedata_list, member):
        """Extract the tarfile member into /assets/img/static."""
        ph_path = '/assets/img/%s' % member.name[len(self.base) + 1:]
        path = self.fs.physical_to_logical(ph_path)

        if self.fs.isfile(path):
            self.journal.append('Updating file \'%s\'' % ph_path)
        else:
            self.journal.append('Inserting file \'%s\'' % ph_path)

        if member.size > MAX_ASSET_UPLOAD_SIZE_K * 1024:
            raise BadImportException(
                'Cannot upload files bigger than %s K' %
                MAX_ASSET_UPLOAD_SIZE_K)

        if self.dry_run:
            return

        filedata_list.append((path, self.archive.extractfile(member)))


# XBlock component tag section


GUEST_USER_SESSION_COOKIE = 'cb-guest-session'
GUEST_USER_SESSION_COOKIE_MAX_AGE_SEC = 48 * 60 * 60  # 48 hours


def get_session_id_for_guest_user(handler):
    session_cookie = handler.request.cookies.get(
        GUEST_USER_SESSION_COOKIE, '')

    # If the session cookie is missing or invalid, generate a new one
    if not re.match('^[0-9a-f]{32}$', session_cookie):
        session_cookie = uuid.uuid4().hex

    handler.response.set_cookie(
        GUEST_USER_SESSION_COOKIE, session_cookie,
        max_age=GUEST_USER_SESSION_COOKIE_MAX_AGE_SEC)

    return 'guest-%s' % session_cookie


class XBlockTag(tags.ContextAwareTag):
    binding_name = 'xblock'

    @classmethod
    def name(cls):
        return 'Embedded XBlocks'

    @classmethod
    def vendor(cls):
        return 'google'

    def get_icon_url(self):
        return RESOURCES_URI + '/xblock.png'

    def get_schema(self, unused_handler):
        """Get the schema for specifying the question."""
        root_list = [
            (unicode(root.id), root.description)
            for root in RootUsageDao.get_all()]
        root_list.sort(key=lambda x: x[1].lower())

        if not root_list:
            return self.unavailable_schema('No XBlocks available')

        reg = schema_fields.FieldRegistry('XBlocks')
        reg.add_property(schema_fields.SchemaField(
            'root_id', messages.XBLOCK_INSTANCE, 'string', optional=True,
            select_data=root_list))
        return reg

    def render(self, node, context):
        root_id = node.attrib.get('root_id')
        usage_id = RootUsageDao.load(root_id).usage_id

        if context.handler.get_user() is not None:
            student_id = context.handler.get_user().user_id()
        else:
            student_id = get_session_id_for_guest_user(context.handler)

        runtime = Runtime(context.handler, student_id=student_id)
        block = runtime.get_block(usage_id)
        fragment = runtime.render(block, 'student_view')

        fragment_list = context.env.get('fragment_list')
        if fragment_list is None:
            fragment_list = []
            context.env['fragment_list'] = fragment_list
        fragment_list.append(fragment)

        return tags.html_string_to_element_tree(
            '<div>%s</div>' % fragment.body_html())

    def rollup_header_footer(self, context):
        wrapper = xblock.fragment.Fragment()
        for frag in context.env.get('fragment_list', []):
            wrapper.add_frag_resources(frag)
        return (
            tags.html_string_to_element_tree(
                '<div>%s</div>' % wrapper.head_html()),
            tags.html_string_to_element_tree(
                '<div>%s</div>' % wrapper.foot_html()))


class XBlockResourcesHandler(tags.ResourcesHandler):
    """Resource handler to serve static files from XBlock workbench."""

    def rebase_path(self, path):
        assert path.startswith(XBLOCK_RESOURCES_URI)
        return os.path.join(
            WORKBENCH_STATIC_PATH,
            os.path.normpath(path[len(XBLOCK_RESOURCES_URI) + 1:]))


class XBlockLocalResourceHandler(webapp2.RequestHandler):
    """Router for requests for a block's local resources."""

    def get(self, block_type, resource):
        xblock_class = xblock.core.XBlock.load_class(block_type)

        mimetype = mimetypes.guess_type(resource)[0]
        if mimetype is None:
            mimetype = 'application/octet-stream'

        self.response.status = 200
        self.response.headers['Content-Type'] = mimetype
        self.response.cache_control.no_cache = None
        self.response.cache_control.public = 'public'
        self.response.cache_control.max_age = 600
        self.response.write(xblock_class.open_local_resource(resource).read())


# Data sanitization section

XBLOCK_EVENT_EXPORT_WHITELIST = {
    'sequential', 'video', 'cbquestion', 'html', 'vertical'}

_orig_event_entity_for_export = None


def _set_new_event_entity_for_export_method():
    """Register the new for_export method on EventEntity."""
    global _orig_event_entity_for_export
    _orig_event_entity_for_export = m_models.EventEntity.for_export
    m_models.EventEntity.for_export = _event_entity_for_export


def _set_orig_event_entity_for_export_method():
    """Restore the original for_export method on EventEntity."""
    global _orig_event_entity_for_export
    m_models.EventEntity.for_export = _orig_event_entity_for_export
    _orig_event_entity_for_export = None


def _event_entity_for_export(model, transform_fn):
    global _orig_event_entity_for_export
    model = _orig_event_entity_for_export(model, transform_fn)

    if model.source == XBLOCK_EVENT_SOURCE_NAME:
        wrapper = transforms.loads(model.data)
        if wrapper.get('type') not in XBLOCK_EVENT_EXPORT_WHITELIST:
            model.data = transforms.dumps({
                'usage': wrapper.get('usage'),
                'type': wrapper.get('type'),
                'event': transform_fn(transforms.dumps(wrapper.get('event')))
            })

    return model


# Module registration section


custom_module = None


def register_module():
    """Registers this module for use."""

    def on_module_disabled():
        _remove_editor_from_dashboard()
        tags.Registry.remove_tag_binding(XBlockTag.binding_name)
        for entity in  [
                dbmodels.DefinitionEntity, dbmodels.UsageEntity,
                dbmodels.KeyValueEntity, RootUsageEntity]:
            courses.COURSE_CONTENT_ENTITIES.remove(entity)
        _set_orig_event_entity_for_export_method()

    def on_module_enabled():
        _add_editor_to_dashboard()
        tags.Registry.add_tag_binding(
            XBlockTag.binding_name, XBlockTag)
        if not django.conf.settings.configured:
            django.conf.settings.configure(
                TEMPLATE_DIRS=[XBLOCK_TEMPLATES_PATH])
        courses.COURSE_CONTENT_ENTITIES += [
            dbmodels.DefinitionEntity, dbmodels.UsageEntity,
            dbmodels.KeyValueEntity, RootUsageEntity]
        _set_new_event_entity_for_export_method()

    global_routes = [
        (RESOURCES_URI + '/.*', tags.ResourcesHandler),
        (XBLOCK_RESOURCES_URI + '/.*', XBlockResourcesHandler),
        (
            XBLOCK_LOCAL_RESOURCES_URI + r'/([^/]*)/(.*)',
            XBlockLocalResourceHandler),
        (MATHJAX_URI + '/(fonts/.*)', sites.make_zip_handler(os.path.join(
            appengine_config.BUNDLE_ROOT, 'lib', 'MathJax-fonts.zip'))),
        (MATHJAX_URI + '/(.*)', sites.make_zip_handler(os.path.join(
            appengine_config.BUNDLE_ROOT, 'lib', 'MathJax.zip')))]

    namespaced_routes = [(HANDLER_URI, XBlockActionHandler)]

    global custom_module

    custom_module = custom_modules.Module(
        'Support for XBlocks within Course Builder',
        'Adds the ability to use XBlock content within Course Builder.',
        global_routes, namespaced_routes,
        notify_module_disabled=on_module_disabled,
        notify_module_enabled=on_module_enabled,
    )

    return custom_module
