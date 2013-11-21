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

"""Functional tests for modules/upload/upload.py."""

__author__ = 'jorr@google.com (John Orr)'

from cStringIO import StringIO
import urllib
import urlparse
from xml.etree import cElementTree

from controllers import sites
from controllers import utils
from models import transforms
from modules.xblock_module import xblock_module
from tests.functional import actions
from xblock import fragment

from google.appengine.api import namespace_manager


def insert_thumbs_block():
    rt = xblock_module.Runtime(MockHandler())
    usage_id = rt.parse_xml_string('<thumbs/>')
    data = {'description': 'an xblock', 'usage_id': usage_id}
    root_usage = xblock_module.RootUsageDto(None, data)
    return xblock_module.RootUsageDao.save(root_usage)


class MockHandler(object):
    def canonicalize_url(self, location):
        return '/new_course' + location


class RuntimeTestCase(actions.TestBase):

    def test_runtime_exports_blocks_with_ids(self):
        """The XBlock runtime should include block ids in XML exports."""
        rt = xblock_module.Runtime(MockHandler())
        usage_id = rt.parse_xml_string('<slider/>')
        xml = '<slider usage_id="%s"/>' % usage_id

        block = rt.get_block(usage_id)
        xml_buffer = StringIO()
        rt.export_to_xml(block, xml_buffer)
        self.assertIn(xml, xml_buffer.getvalue())

    def test_runtime_imports_blocks_with_ids(self):
        """The workbench should update blocks in place when they have ids."""
        rt = xblock_module.Runtime(MockHandler())
        usage_id = rt.parse_xml_string('<html>foo</html>')
        self.assertEqual('foo', rt.get_block(usage_id).content)

        xml = '<html usage_id="%s">bar</html>' % usage_id
        new_usage_id = rt.parse_xml_string(xml)
        self.assertEqual(usage_id, new_usage_id)
        self.assertEqual('bar', rt.get_block(usage_id).content)

    def test_rendered_blocks_have_js_dependencies_included(self):
        rt = xblock_module.Runtime(MockHandler(), student_id='s23')
        usage_id = rt.parse_xml_string('<slider/>')
        block = rt.get_block(usage_id)
        frag = rt.render(block, 'student_view')
        self.assertIn('js/vendor/jquery.min.js', frag.foot_html())
        self.assertIn('js/vendor/jquery.cookie.js', frag.foot_html())
        self.assertIn('js/runtime/1.js', frag.foot_html())

    def test_handler_url(self):
        xsrf_token = utils.XsrfTokenManager.create_xsrf_token(
            xblock_module.XBLOCK_XSRF_TOKEN_NAME)
        rt = xblock_module.Runtime(MockHandler(), student_id='s23')
        usage_id = rt.parse_xml_string('<thumbs/>')
        block = rt.get_block(usage_id)
        url = urlparse.urlparse(rt.handler_url(block, 'vote'))
        self.assertEqual('/new_course/modules/xblock_module/handler', url.path)
        query = urlparse.parse_qs(url.query)
        self.assertEqual(block.scope_ids.usage_id, query['usage'][0])
        self.assertEqual('vote', query['handler'][0])
        self.assertEqual(xsrf_token, query['xsrf_token'][0])


class XBlockActionHandlerTestCase(actions.TestBase):
    """Functional tests for the XBlock callback handler."""

    def test_post(self):
        actions.login('user@example.com')
        rt = xblock_module.Runtime(
            MockHandler(), student_id='user@example.com')
        usage_id = rt.parse_xml_string('<thumbs/>')
        self.assertEqual(0, rt.get_block(usage_id).upvotes)
        xsrf_token = utils.XsrfTokenManager.create_xsrf_token(
            xblock_module.XBLOCK_XSRF_TOKEN_NAME)

        params = {
            'usage': usage_id,
            'handler': 'vote',
            'xsrf_token': xsrf_token}
        response = self.post(
            '%s?%s' % (xblock_module.HANDLER_URI, urllib.urlencode(params)),
            '{"voteType":"up"}', {})
        self.assertEqual('{"down": 0, "up": 1}', response.body)
        self.assertEqual(1, rt.get_block(usage_id).upvotes)

    def test_post_bad_xsrf_rejected(self):
        """Callbacks with bad XSRF token should be rejected."""
        actions.login('user@example.com')
        rt = xblock_module.Runtime(
            MockHandler(), student_id='user@example.com')
        usage_id = rt.parse_xml_string('<thumbs/>')

        params = {
            'usage': usage_id,
            'handler': 'vote',
            'xsrf_token': 'bad_token'}
        response = self.testapp.post(
            '%s?%s' % (xblock_module.HANDLER_URI, urllib.urlencode(params)),
            '{"vote_type":"up"}', {},
            expect_errors=True)
        self.assertEqual(400, response.status_int)

    def test_post_without_user_rejected(self):
        rt = xblock_module.Runtime(MockHandler())
        usage_id = rt.parse_xml_string('<thumbs/>')

        params = {
            'usage': usage_id,
            'handler': 'vote',
            'xsrf_token': 'bad_token'}
        response = self.testapp.post(
            '%s?%s' % (xblock_module.HANDLER_URI, urllib.urlencode(params)),
            '{"vote_type":"up"}', {},
            expect_errors=True)
        self.assertEqual(403, response.status_int)


class RootUsageTestCase(actions.TestBase):
    """Functional tests for the root usage DAO and DTO."""

    def test_root_usage_properties(self):
        data = {'description': 'an xblock', 'usage_id': '123'}
        root_usage = xblock_module.RootUsageDto(None, data)
        self.assertEqual('an xblock', root_usage.description)
        self.assertEqual('123', root_usage.usage_id)

    def test_root_usage_crud(self):
        data = {'description': 'an xblock', 'usage_id': '123'}
        root_usage = xblock_module.RootUsageDto(None, data)
        root_usage_id = xblock_module.RootUsageDao.save(root_usage)
        self.assertTrue(root_usage_id is not None)

        root_usage = xblock_module.RootUsageDto(root_usage_id, None)
        root_usage = xblock_module.RootUsageDao.load(root_usage_id)
        self.assertEqual(data, root_usage.dict)

        xblock_module.RootUsageDao.delete(root_usage)
        root_usage = xblock_module.RootUsageDao.load(root_usage_id)
        self.assertIsNone(root_usage)


class XBlockEditorTestCase(actions.TestBase):
    """Functional tests for the XBlock editor in the dashboard."""

    def setUp(self):
        super(XBlockEditorTestCase, self).setUp()
        self.base = '/test'
        sites.setup_courses('course:/test::ns_test, course:/:/')
        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_test')
        actions.login('admin@example.com', is_admin=True)

    def tearDown(self):
        namespace_manager.set_namespace(self.old_namespace)
        super(XBlockEditorTestCase, self).tearDown()

    def test_xblock_section_present_in_assets(self):
        response = self.get('dashboard?action=assets')
        self.assertIn('<h3>XBlocks</h3>', response.body)

        self.assertNotIn('an xblock', response.body)
        insert_thumbs_block()
        response = self.get('dashboard?action=assets')
        self.assertIn('an xblock', response.body)

    def test_add_xblock_editor_present(self):
        response = self.get('dashboard?action=assets')
        self.assertIn(
            'href="dashboard?action=add_xblock">Add XBlock</a>', response.body)

        response = self.get('dashboard?action=add_xblock')
        self.assertIn('<h2>Add XBlock</h2>', response.body)

    def test_edit_xblock_editor_present(self):
        root_usage_id = insert_thumbs_block()
        editor_url = 'dashboard?action=edit_xblock&amp;key=%s' % root_usage_id

        response = self.get('dashboard?action=assets')
        self.assertIn('href="%s">[Edit]</a>' % editor_url, response.body)

        response = self.get(editor_url)
        self.assertIn('<h2>Edit XBlock</h2>', response.body)

    def test_editor_unavailable_when_module_disabled(self):
        xblock_module.custom_module.disable()
        response = self.get('dashboard?action=assets')
        self.assertNotIn('<h3>XBlocks</h3>', response.body)
        self.assertNotIn(
            'href="dashboard?action=add_xblock">Add XBlock</a>', response.body)
        self.assertNotIn('dashboard?action=edit_xblock', response.body)
        xblock_module.custom_module.enable()


class XBlockEditorRESTHandlerTestCase(actions.TestBase):
    """Functional tests for the dashboard XBlock editor's REST handler."""

    def setUp(self):
        super(XBlockEditorRESTHandlerTestCase, self).setUp()
        actions.login('admin@example.com', is_admin=True)
        self.xsrf_token = utils.XsrfTokenManager.create_xsrf_token(
            xblock_module.XBlockEditorRESTHandler.XSRF_TOKEN)

    def get_request(
        self, xsrf_token, description='html block',
        xml='<html>test html</html>'):

        request = {
            'key': '',
            'payload': transforms.dumps({
                'xml': xml,
                'description': description}),
            'xsrf_token': xsrf_token}
        return {'request': transforms.dumps(request)}

    def get_xsrf_token(self):
        return utils.XsrfTokenManager.create_xsrf_token(
            xblock_module.XBlockEditorRESTHandler.XSRF_TOKEN)

    def delete(self, url, **kwargs):
        url = self.canonicalize(url)
        response = self.testapp.delete(url, **kwargs)
        return self.hook_response(response)

    def test_get(self):
        root_usage_id = insert_thumbs_block()
        response = self.get('rest/xblock?key=%s' % root_usage_id)
        resp_dict = transforms.loads(response.body)
        self.assertEqual(200, resp_dict['status'])
        self.assertEqual('Success', resp_dict['message'])
        self.assertIsNotNone(resp_dict['xsrf_token'])

        payload = transforms.loads(resp_dict['payload'])
        self.assertEqual('an xblock', payload['description'])
        self.assertIn('<thumbs usage_id=', payload['xml'])

    def test_get_fails_without_login(self):
        actions.logout()
        root_usage_id = insert_thumbs_block()
        response = self.get('rest/xblock?key=%s' % root_usage_id)
        resp_dict = transforms.loads(response.body)
        self.assertEqual(401, resp_dict['status'])

    def test_put(self):
        """Test the happy case of PUT accepting and inserting XBlock XML."""
        response = self.put('rest/xblock', self.get_request(self.xsrf_token))
        resp_dict = transforms.loads(response.body)
        self.assertEqual(200, resp_dict['status'])
        self.assertEqual('Saved.', resp_dict['message'])

        payload = transforms.loads(resp_dict['payload'])
        root_usage_id = payload['key']
        self.assertIsNotNone(root_usage_id)

        # Confirm the block was stored
        root_usage = xblock_module.RootUsageDao.load(root_usage_id)
        block = xblock_module.Runtime(
            MockHandler()).get_block(root_usage.usage_id)
        self.assertEqual('test html', block.content)

    def test_put_fails_with_bad_xsrf_token(self):
        response = self.put('rest/xblock', self.get_request('bad_token'))
        resp_dict = transforms.loads(response.body)
        self.assertEqual(403, resp_dict['status'])

    def test_put_fails_without_login(self):
        actions.logout()
        xsrf_token = self.get_xsrf_token()
        response = self.put('rest/xblock', self.get_request(xsrf_token))
        resp_dict = transforms.loads(response.body)
        self.assertEqual(401, resp_dict['status'])

    def test_put_fails_without_description(self):
        response = self.put(
            'rest/xblock', self.get_request(self.xsrf_token, description=''))
        resp_dict = transforms.loads(response.body)
        self.assertEqual(412, resp_dict['status'])
        self.assertEqual('Missing description field', resp_dict['message'])

    def test_put_fails_with_invalid_xml(self):
        response = self.put(
            'rest/xblock', self.get_request(self.xsrf_token, xml='<html'))
        resp_dict = transforms.loads(response.body)
        self.assertEqual(412, resp_dict['status'])

    def test_put_fails_with_empty_xml(self):
        response = self.put(
            'rest/xblock', self.get_request(self.xsrf_token, xml=''))
        resp_dict = transforms.loads(response.body)
        self.assertEqual(412, resp_dict['status'])

    def test_delete(self):
        root_usage_id = insert_thumbs_block()
        params = {
            'xsrf_token': self.xsrf_token,
            'key': root_usage_id}
        response = self.delete('rest/xblock?%s' % urllib.urlencode(params))
        resp_dict = transforms.loads(response.body)
        self.assertEqual(200, resp_dict['status'])
        self.assertEqual('Deleted.', resp_dict['message'])

        # Confirm deletion took place
        self.assertIsNone(xblock_module.RootUsageDao.load(root_usage_id))

    def test_delete_fails_with_bad_xsrf_token(self):
        root_usage_id = insert_thumbs_block()
        params = {
            'xsrf_token': 'bad_xsrf_token',
            'key': root_usage_id}
        response = self.delete('rest/xblock?%s' % urllib.urlencode(params))
        resp_dict = transforms.loads(response.body)
        self.assertEqual(403, resp_dict['status'])

    def test_delete_fails_without_login(self):
        actions.logout()
        root_usage_id = insert_thumbs_block()
        params = {
            'xsrf_token': self.get_xsrf_token(),
            'key': root_usage_id}
        response = self.delete('rest/xblock?%s' % urllib.urlencode(params))
        resp_dict = transforms.loads(response.body)
        self.assertEqual(401, resp_dict['status'])


class XBlockTagTestCase(actions.TestBase):
    """Functional tests for the XBlock tag."""

    class Mockhandler(object):
        def get_user(self):
            class User(object):
                def user_id(self):
                    return 'student@example.com'
            return User()

    def setUp(self):
        super(XBlockTagTestCase, self).setUp()
        actions.login('student@example.com', is_admin=False)

    def test_render(self):
        root_usage_id = insert_thumbs_block()

        node = cElementTree.XML(
            '<xblock root_id="%s"></xblock>' % root_usage_id)
        handler = XBlockTagTestCase.Mockhandler()
        cxt = xblock_module.XBlockTag.Context(handler, {})
        node = xblock_module.XBlockTag().render(node, cxt)

        self.assertEqual('div', node.tag)
        self.assertEqual(1, len(node))

        self.assertEqual('div', node[0].tag)
        self.assertEqual(1, len(node[0]))

        node = node[0][0]
        self.assertEqual('div', node.tag)
        self.assertEqual('xblock', node.attrib['class'])
        self.assertEqual('thumbs', node.attrib['data-block-type'])

        xsrf_token = utils.XsrfTokenManager.create_xsrf_token(
            xblock_module.XBLOCK_XSRF_TOKEN_NAME)
        self.assertEqual(xsrf_token, node.attrib['data-xsrf-token'])

        self.assertEqual(1, len(cxt.env['fragment_list']))
        self.assertIsInstance(cxt.env['fragment_list'][0], fragment.Fragment)

    def test_rollup_header_footer(self):
        """Rollup should de-dup resources in the fragments."""
        frag_1 = fragment.Fragment()
        frag_1.add_css_url('A.css')
        frag_1.add_css_url('B.css')

        frag_2 = fragment.Fragment()
        frag_2.add_css_url('A.css')
        frag_2.add_css_url('C.css')

        handler = XBlockTagTestCase.Mockhandler()
        cxt = xblock_module.XBlockTag.Context(handler, {})
        cxt.env['fragment_list'] = [frag_1, frag_2]

        head, unused_foot = xblock_module.XBlockTag().rollup_header_footer(cxt)

        self.assertEqual(1, len(head.findall('.//link[@href="A.css"]')))
        self.assertEqual(1, len(head.findall('.//link[@href="B.css"]')))
        self.assertEqual(1, len(head.findall('.//link[@href="C.css"]')))


class XBlockResourceHandlerTestCase(actions.TestBase):
    """Functional tests for the handler for XBlock resources."""

    def test_serves_xblock_workbench_resources(self):
        response = self.get(
            '/modules/xblock_module/xblock_resources/css/workbench.css')
        self.assertEqual(200, response.status_int)
