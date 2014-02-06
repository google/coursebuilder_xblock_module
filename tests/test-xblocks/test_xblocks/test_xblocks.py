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

"""XBlocks used in testing."""

__author__ = 'John Orr (jorr@google.com)'


import os
import cb_xblocks_core.cb_xblocks_core
import json
import webob

from xblock.core import XBlock
from xblock.fields import Integer, Scope, String
from xblock.fragment import Fragment


@XBlock.needs('jinja')
class TestFieldsBlock(XBlock):

    content = String(scope=Scope.content, default='content_value')
    settings = String(scope=Scope.settings, default='settings_value')
    user_state = String(scope=Scope.user_state, default='user_state_value')
    user_state_summary = Integer(scope=Scope.user_state_summary, default=0)

    def __init__(self, *args, **kwargs):
        super(TestFieldsBlock, self).__init__(*args, **kwargs)
        self.templates_dirs = [
            os.path.join(os.path.dirname(__file__), 'templates')]
        self.get_template = self.runtime.service(self, 'jinja')

    def student_view(self, context=None):
        frag = Fragment()
        template = self.get_template('test_fields.html', self.templates_dirs)
        template_values = {
            'usage_id': self.scope_ids.usage_id,
            'content':self.content,
            'settings':self.settings,
            'user_state':self.user_state,
            'user_state_summary':self.user_state_summary}
        frag.add_content(
            template.render(template_values))
        frag.initialize_js('TestFieldsBlock')
        frag.add_javascript('function TestFieldsBlock(rt, elt) {}')
        return frag

    def json_response(self, json_dict):
        return webob.Response(
            body=json.dumps(json_dict), content_type='application/json')

    @XBlock.handler
    def set_user_state(self, request, suffix=''):
        self.user_state = request.params['value']
        return self.json_response({'status': 'ok'})

    @XBlock.handler
    def increment_user_state_summary(self, request, suffix=''):
        self.user_state_summary += 1
        return self.json_response(
            {'status': 'ok', 'value': self.user_state_summary})
