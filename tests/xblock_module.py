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
import os
import re
import urllib
import urlparse
from xml.etree import cElementTree

from controllers import sites
from controllers import utils
import html5lib
from models import courses
from models import transforms
import models.models as m_models
from modules.xblock_module import dbmodels
from modules.xblock_module import xblock_module
from tools.etl import etl
import xblock
from xblock import fragment

from tests.functional import actions
from tests.functional import test_classes

from google.appengine.api import files
from google.appengine.api import namespace_manager
from google.appengine.api import users
from google.appengine.ext import ndb

THUMBS_ENTRY_POINT = 'thumbs = thumbs:ThumbsBlock'


def insert_thumbs_block():
    rt = xblock_module.Runtime(MockHandler(), is_admin=True)
    usage_id = parse_xml_string(rt, '<thumbs/>')
    data = {'description': 'an xblock', 'usage_id': usage_id}
    root_usage = xblock_module.RootUsageDto(None, data)
    return xblock_module.RootUsageDao.save(root_usage)


def parse_html_string(html_doc):
    parser = html5lib.HTMLParser(
        tree=html5lib.treebuilders.getTreeBuilder('etree', cElementTree),
        namespaceHTMLElements=False)
    return parser.parse(html_doc)


@ndb.toplevel
def parse_xml_string(rt, xml_str, dry_run=False):
    return rt.parse_xml_string(xml_str, None, dry_run=dry_run)


class MockHandler(object):

    def canonicalize_url(self, location):
        return '/new_course' + location


class TestBase(actions.TestBase):

    def setUp(self):
        super(TestBase, self).setUp()
        # Whitelist the thumbs block for testing
        if THUMBS_ENTRY_POINT not in xblock_module.XBLOCK_WHITELIST:
            xblock_module.XBLOCK_WHITELIST.append(THUMBS_ENTRY_POINT)

    def tearDown(self):
        if THUMBS_ENTRY_POINT in xblock_module.XBLOCK_WHITELIST:
            xblock_module.XBLOCK_WHITELIST.remove(THUMBS_ENTRY_POINT)
            xblock.core.XBlock._plugin_cache = None  # pylint: disable=protected-access
        super(TestBase, self).tearDown()


class DataMigrationTests(TestBase):
    """Functional tests for data migration with import and ETL."""

    def setUp(self):
        super(DataMigrationTests, self).setUp()
        self.old_namespace = namespace_manager.get_namespace()

    def tearDown(self):
        namespace_manager.set_namespace(self.old_namespace)
        super(DataMigrationTests, self).tearDown()

    def test_course_import(self):
        """Confirm course import preserves XBlock data."""

        sites.setup_courses('course:/a::ns_a, course:/b::ns_b, course:/:/')

        app_context_a, app_context_b, _ = sites.get_all_courses()
        course_b = courses.Course(None, app_context=app_context_b)

        # Switch to Course A and insert a CB XBlock usage
        namespace_manager.set_namespace('ns_a')

        rt = xblock_module.Runtime(MockHandler(), is_admin=True)
        usage_id = parse_xml_string(rt, '<html>Text</html>')
        data = {'description': 'an xblock', 'usage_id': usage_id}
        root_usage = xblock_module.RootUsageDto(None, data)
        key = xblock_module.RootUsageDao.save(root_usage)

        # Switch to Course B and import
        namespace_manager.set_namespace('ns_b')
        self.assertEqual(0, len(xblock_module.RootUsageDao.get_all()))

        errors = []
        course_b.import_from(app_context_a, errors)
        if errors:
            raise Exception(errors)

        # Confirm the import worked
        self.assertEqual(1, len(xblock_module.RootUsageDao.get_all()))
        root_usage = xblock_module.RootUsageDao.load(key)
        rt = xblock_module.Runtime(MockHandler())
        block = rt.get_block(root_usage.usage_id)
        self.assertEqual('html', block.xml_element_name())
        self.assertEqual('Text', block.content)

    def test_etl_roundtrip(self):
        """Confirm that XBlock data can be exported and imported with ETL."""

        sites.setup_courses('course:/a::ns_a, course:/b::ns_b, course:/:/')

        # Switch to Course A and insert a CB XBlock usage
        namespace_manager.set_namespace('ns_a')

        rt = xblock_module.Runtime(MockHandler(), is_admin=True)
        usage_id = parse_xml_string(rt, '<html>Text</html>')
        data = {'description': 'an xblock', 'usage_id': usage_id}
        root_usage = xblock_module.RootUsageDto(None, data)
        key = xblock_module.RootUsageDao.save(root_usage)

        # Switch to Course B and confirm there's no XBlock data yet
        namespace_manager.set_namespace('ns_b')
        self.assertEqual(0, len(xblock_module.RootUsageDao.get_all()))

        # Download course data from Course A with ETL
        archive_path = os.path.join(self.test_tempdir, 'archive.zip')
        args = etl.PARSER.parse_args([
            etl._MODE_DOWNLOAD, etl._TYPE_COURSE,  # pylint: disable=protected-access
            '--archive_path', archive_path, '/a', 'mycourse', 'localhost:8080'])
        etl.main(args, environment_class=test_classes.FakeEnvironment)

        # Upload the archive zip file into Course B with ETL
        args = etl.PARSER.parse_args([
            etl._MODE_UPLOAD, etl._TYPE_COURSE,  #  pylint: disable=protected-access
            '--archive_path', archive_path, '/b', 'mycourse', 'localhost:8080'])
        etl.main(args, environment_class=test_classes.FakeEnvironment)

        # Confirm the XBlock data was migrated correctly
        self.assertEqual(1, len(xblock_module.RootUsageDao.get_all()))
        root_usage = xblock_module.RootUsageDao.load(key)
        rt = xblock_module.Runtime(MockHandler())
        block = rt.get_block(root_usage.usage_id)
        self.assertEqual('html', block.xml_element_name())
        self.assertEqual('Text', block.content)


class RuntimeTestCase(TestBase):
    """Functional tests for the XBlock runtime."""

    def test_runtime_exports_blocks_with_ids(self):
        """The XBlock runtime should include block ids in XML exports."""
        rt = xblock_module.Runtime(MockHandler(), is_admin=True)
        usage_id = parse_xml_string(rt, '<html>text</html>')
        xml = '<html usage_id="%s">text</html>' % usage_id

        block = rt.get_block(usage_id)
        xml_buffer = StringIO()
        rt.export_to_xml(block, xml_buffer)
        self.assertIn(xml, xml_buffer.getvalue())

    def test_runtime_updates_blocks_with_ids(self):
        """The workbench should update blocks in place when they have ids."""
        rt = xblock_module.Runtime(MockHandler(), is_admin=True)
        usage_id = parse_xml_string(rt, '<html>foo</html>')
        self.assertEqual('foo', rt.get_block(usage_id).content)

        xml = '<html usage_id="%s">bar</html>' % usage_id
        new_usage_id = parse_xml_string(rt, xml)
        self.assertEqual(usage_id, new_usage_id)
        self.assertEqual('bar', rt.get_block(usage_id).content)

    def test_runtime_removes_orphaned_blocks_on_update(self):
        """Remove a child on block update and see it removed in datastore."""
        block_with_child_xml = """
<vertical usage_id="vertical_id">
  <html usage_id="html_id">text</html>
</vertical>"""
        block_without_child_xml = """
<vertical usage_id="vertical_id">
</vertical>"""

        rt = xblock_module.Runtime(MockHandler(), is_admin=True)
        parse_xml_string(rt, block_with_child_xml)
        vertical = rt.get_block('vertical_id')
        self.assertEqual(1, len(vertical.children))

        # Merge in same vertical, with html block deleted and check it is
        # deleted from the block tree
        rt = xblock_module.Runtime(MockHandler(), is_admin=True)
        parse_xml_string(rt, block_without_child_xml)
        vertical = rt.get_block('vertical_id')
        self.assertEqual(0, len(vertical.children))

        # However the html block is not deleted from the datastore, just
        # unlinked from the content tree.
        html = rt.get_block('html_id')
        self.assertEqual('html', html.xml_element_name())
        self.assertEqual('text', html.content)

    def test_runtime_should_import_blocks_with_specified_ids(self):
        """The workbench shouild create a new block with a given id."""
        rt = xblock_module.Runtime(MockHandler(), is_admin=True)
        parse_xml_string(rt, '<html usage_id="my_usage_id">foo</html>')
        block = rt.get_block('my_usage_id')
        self.assertEqual('html', block.xml_element_name())
        self.assertEqual('foo', block.content)

    def test_rendered_blocks_have_js_dependencies_included(self):
        rt = xblock_module.Runtime(MockHandler(), is_admin=True)
        usage_id = parse_xml_string(rt, '<thumbs/>')
        rt = xblock_module.Runtime(MockHandler(), student_id='s23')
        block = rt.get_block(usage_id)
        frag = rt.render(block, 'student_view')
        self.assertIn('js/vendor/jquery.min.js', frag.foot_html())
        self.assertIn('js/vendor/jquery.cookie.js', frag.foot_html())
        self.assertIn('js/runtime/1.js', frag.foot_html())

    def test_handler_url(self):
        xsrf_token = utils.XsrfTokenManager.create_xsrf_token(
            xblock_module.XBLOCK_XSRF_TOKEN_NAME)
        rt = xblock_module.Runtime(MockHandler(), is_admin=True)
        usage_id = parse_xml_string(rt, '<thumbs/>')
        rt = xblock_module.Runtime(MockHandler(), student_id='s23')
        block = rt.get_block(usage_id)
        url = urlparse.urlparse(rt.handler_url(block, 'vote'))
        self.assertEqual('/new_course/modules/xblock_module/handler', url.path)
        query = urlparse.parse_qs(url.query)
        self.assertEqual(block.scope_ids.usage_id, query['usage'][0])
        self.assertEqual('vote', query['handler'][0])
        self.assertEqual(xsrf_token, query['xsrf_token'][0])

    def test_runtime_prevents_student_writes_to_non_student_fields(self):
        rt = xblock_module.Runtime(MockHandler(), is_admin=True)
        usage_id = parse_xml_string(rt, '<html>Test</html>')

        # Load the block in student role
        rt = xblock_module.Runtime(MockHandler(), student_id='s23')
        block = rt.get_block(usage_id)
        self.assertEqual('Test', block.content)
        block.content = 'Something else'
        try:
            block.save()
            self.fail('Expected InvalidScopeError')
        except xblock.exceptions.InvalidScopeError:
            pass  # Expected exception

        # Load the block in admin role
        rt = xblock_module.Runtime(MockHandler(), is_admin=True)
        block = rt.get_block(usage_id)
        block.content = 'Something else'
        block.save()  # No exception

    def test_runtime_prevents_loading_of_non_whitelisted_blocks(self):
        rt = xblock_module.Runtime(MockHandler(), is_admin=True)

        # Loading thumbs block succeeds when it is whitelisted
        unused_usage_id = parse_xml_string(rt, '<thumbs/>')

        # Loading thumbs block fails when it is not whitelisted
        xblock_module.XBLOCK_WHITELIST.remove(THUMBS_ENTRY_POINT)
        xblock.core.XBlock._plugin_cache = None  # pylint: disable=protected-access
        try:
            unused_usage_id = parse_xml_string(rt, '<thumbs/>')
            self.fail('Expected ForbiddenXBlockError')
        except xblock_module.ForbiddenXBlockError:
            pass  # Expected exception


class XBlockActionHandlerTestCase(TestBase):
    """Functional tests for the XBlock callback handler."""

    def test_post(self):
        actions.login('user@example.com')
        rt = xblock_module.Runtime(MockHandler(), is_admin=True)
        usage_id = parse_xml_string(rt, '<thumbs/>')
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
        rt = xblock_module.Runtime(MockHandler(), is_admin=True)
        usage_id = parse_xml_string(rt, '<thumbs/>')

        params = {
            'usage': usage_id,
            'handler': 'vote',
            'xsrf_token': 'bad_token'}
        response = self.testapp.post(
            '%s?%s' % (xblock_module.HANDLER_URI, urllib.urlencode(params)),
            '{"vote_type":"up"}', {},
            expect_errors=True)
        self.assertEqual(400, response.status_int)


class GuestUserTestCase(TestBase):
    """Functional tests for the handling of logged-in and guest users."""

    def setUp(self):
        super(GuestUserTestCase, self).setUp()

        actions.login('user@example.com', is_admin=True)

        # Create a course in namespace "test"
        sites.setup_courses('course:/test::ns_test, course:/:/')
        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_test')
        actions.login('admin@example.com', is_admin=True)

        # Add an xblock containing a seqeunce of html blocks
        rt = xblock_module.Runtime(MockHandler(), is_admin=True)
        self.usage_id = parse_xml_string(
            rt, '<sequential><html>1</html><html>2</html></sequential>')
        data = {'description': 'an xblock', 'usage_id': self.usage_id}
        root_usage = xblock_module.RootUsageDto(None, data)
        root_usage_id = xblock_module.RootUsageDao.save(root_usage)

        # Add a unit and a lesson to the course
        app_context = sites.get_all_courses()[0]
        self.course = courses.Course(None, app_context=app_context)
        self.unit = self.course.add_unit()
        self.unit.now_available = True
        self.lesson = self.course.add_lesson(self.unit)

        # The lesson displays the xblock
        self.lesson.now_available = True
        self.lesson.objectives = '<xblock root_id="%s"/>' % root_usage_id

        # Make the course available.
        self.get_environ_old = sites.ApplicationContext.get_environ

        def get_environ_new(cxt):
            environ = self.get_environ_old(cxt)
            environ['course']['now_available'] = True
            return environ

        sites.ApplicationContext.get_environ = get_environ_new

        self.course.save()

        # Ensure the user is logged out
        actions.logout()

    def tearDown(self):
        namespace_manager.set_namespace(self.old_namespace)
        sites.ApplicationContext.get_environ = self.get_environ_old
        super(GuestUserTestCase, self).tearDown()

    def _get_xblock_in_lesson(self):
        lesson_uri = '/test/unit?unit=%s&lesson=%s' % (
            self.unit.unit_id, self.lesson.lesson_id)
        response = self.get(lesson_uri)
        root = parse_html_string(response.body)
        sequence_elt = root.find(
            './/*[@class="gcb-lesson-content"]/div/div/div[@class="xblock"]')
        self.assertEqual('sequential', sequence_elt.attrib['data-block-type'])
        self.assertEqual(self.usage_id, sequence_elt.attrib['data-usage'])
        return sequence_elt

    def _post_tab_position(self, xsrf_token, position):
        params = {
            'usage': self.usage_id,
            'handler': 'on_select',
            'xsrf_token': xsrf_token}
        response = self.testapp.post(
            '/test%s?%s' % (
                xblock_module.HANDLER_URI, urllib.urlencode(params)),
            '{"position":%s}' % position, {})
        self.assertEqual('{"position": %s}' % position, response.body)

    def _extract_position(self, sequence_elt):
        return int(sequence_elt.find(
            './div[@class="sequence_block"]').attrib['data-position'])

    def test_guest_user(self):
        self.assertIsNone(users.get_current_user())

        # The guest user can view the page
        sequence_elt = self._get_xblock_in_lesson()
        xsrf_token = sequence_elt.attrib['data-xsrf-token']
        self.assertEqual(0, self._extract_position(sequence_elt))

        # The response has a coookie with a temporary user id
        session_cookie = self.testapp.cookies['cb-guest-session']
        self.assertRegexpMatches(session_cookie, r'^[0-9a-f]{32}$')

        # Click on the second tab
        self._post_tab_position(xsrf_token, 1)

        # Cookie hasn't changed
        self.assertEqual(
            session_cookie, self.testapp.cookies['cb-guest-session'])

        # Reload the page, and expect that the selected tab will have changed
        sequence_elt = self._get_xblock_in_lesson()
        self.assertEqual(1, self._extract_position(sequence_elt))

        # There was an event recorded
        student_id = 'guest-%s' % session_cookie
        event = m_models.EventEntity.all().fetch(1)[0]
        self.assertEqual(student_id, event.user_id)

        # The state is stored under temp student_id
        rt = xblock_module.Runtime(MockHandler(), student_id=student_id)
        self.assertEqual(1, rt.get_block(self.usage_id).position)

    def test_logged_in_user(self):
        actions.login('user@example.com')
        student_id = users.get_current_user().user_id()
        self.assertIsNotNone(student_id)

        # The user can view the page
        sequence_elt = self._get_xblock_in_lesson()
        xsrf_token = sequence_elt.attrib['data-xsrf-token']
        self.assertEqual(0, self._extract_position(sequence_elt))

        # The response has no session cookie
        self.assertNotIn('cb-guest-session', self.testapp.cookies)

        # Click on the second tab
        self._post_tab_position(xsrf_token, 1)

        # Still no session cookie
        self.assertNotIn('cb-guest-session', self.testapp.cookies)

        # Reload the page, and expect that the selected tab will have changed
        sequence_elt = self._get_xblock_in_lesson()
        self.assertEqual(1, self._extract_position(sequence_elt))

        # There was an event recorded
        event = m_models.EventEntity.all().fetch(1)[0]
        self.assertEqual(student_id, event.user_id)

        # The state is stored under student_id
        rt = xblock_module.Runtime(MockHandler(), student_id=student_id)
        self.assertEqual(1, rt.get_block(self.usage_id).position)


class RootUsageTestCase(TestBase):
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


class XBlockEditorTestCase(TestBase):
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
        self.assertIn('Add XBlock', response.body)

    def test_import_xblock_button(self):
        """Import button present if class empty, absent if it has content."""

        def get_import_button():
            root = parse_html_string(self.get('dashboard?action=assets').body)
            return root.find('.//*[@id="gcb-main-content"]/a[1]')

        button = get_import_button()
        self.assertEquals('Import', button.text)
        self.assertEquals(
            'dashboard?action=import_xblock', button.attrib['href'])

        # Add some content to the class. Import should not appear now.
        app_context = sites.get_all_courses()[0]
        course = courses.Course(None, app_context=app_context)
        unused_unit = course.add_unit()
        course.save()

        button = get_import_button()
        self.assertEquals('Merge', button.text)
        self.assertEquals(
            'dashboard?action=import_xblock', button.attrib['href'])

    def test_edit_xblock_editor_present(self):
        root_usage_id = insert_thumbs_block()
        editor_url = 'dashboard?action=edit_xblock&amp;key=%s' % root_usage_id

        response = self.get('dashboard?action=assets')
        self.assertIn('href="%s">[Edit]</a>' % editor_url, response.body)

        response = self.get(editor_url)
        self.assertIn('Edit XBlock', response.body)

    def test_editor_and_import_unavailable_when_module_disabled(self):
        xblock_module.custom_module.disable()
        response = self.get('dashboard?action=assets')
        self.assertNotIn('<h3>XBlocks</h3>', response.body)
        self.assertNotIn(
            'href="dashboard?action=add_xblock">Add XBlock</a>', response.body)
        self.assertNotIn(
            'href="dashboard?action=import_xblock">Import</a>', response.body)
        self.assertNotIn('dashboard?action=edit_xblock', response.body)
        xblock_module.custom_module.enable()


class XBlockEditorRESTHandlerTestCase(TestBase):
    """Functional tests for the dashboard XBlock editor's REST handler."""

    def setUp(self):
        super(XBlockEditorRESTHandlerTestCase, self).setUp()
        actions.login('admin@example.com', is_admin=True)
        self.xsrf_token = utils.XsrfTokenManager.create_xsrf_token(
            xblock_module.XBlockEditorRESTHandler.XSRF_TOKEN)

    @classmethod
    def get_request(
        cls, xsrf_token, description='html block',
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


class XBlockArchiveRESTHandlerTestCase(TestBase):
    """Functional tests for the XBlock archive importer REST handler."""

    def setUp(self):
        super(XBlockArchiveRESTHandlerTestCase, self).setUp()
        self.testbed.init_blobstore_stub()
        self.testbed.init_files_stub()
        self.base = '/test'
        sites.setup_courses('course:/test::ns_test, course:/:/')
        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_test')
        actions.login('admin@example.com', is_admin=True)
        self.xsrf_token = utils.XsrfTokenManager.create_xsrf_token(
            xblock_module.XBlockArchiveRESTHandler.XSRF_TOKEN)

    def tearDown(self):
        namespace_manager.set_namespace(self.old_namespace)
        super(XBlockArchiveRESTHandlerTestCase, self).tearDown()

    def get_request(self, xsrf_token=None, upload=None, dry_run=False):
        xsrf_token = xsrf_token or self.xsrf_token
        filename = upload.filename if upload else ''
        request = {
            'key': '',
            'payload': transforms.dumps({
                'file': filename,
                'dry_run': dry_run}),
            'xsrf_token': xsrf_token}
        return {
            'request': transforms.dumps(request),
            'file': upload}

    def get_response_dict(self, response_str):
        response_xml = cElementTree.XML(response_str)
        response_dict = {}
        for child in response_xml:
            response_dict[child.tag] = child.text
        return response_dict

    def test_rest_handler_provides_upload_and_poller_url(self):
        response = self.get('rest/xblock_archive')
        resp_dict = transforms.loads(response.body)
        self.assertEqual(200, resp_dict['status'])
        payload = transforms.loads(resp_dict['payload'])
        self.assertTrue(
            payload['upload_url'].startswith('http://localhost/_ah/upload/'))
        self.assertEquals(
            '/test/rest/xblock_archive_progress', payload['poller_url'])

    def test_post_fails_with_bad_xsrf_token(self):
        response = self.post(
            'rest/xblock_archive', self.get_request(xsrf_token='bad_token'))
        resp_dict = transforms.loads(response.body)
        self.assertEqual(403, resp_dict['status'])

    def test_post_fails_without_login(self):
        actions.logout()
        response = self.post(
            'rest/xblock_archive', self.get_request(), expect_errors=True)
        self.assertEqual(404, response.status_int)

    def test_post_fails_with_missing_attachment(self):
        response = self.post('rest/xblock_archive', self.get_request())
        resp_dict = self.get_response_dict(response.body)
        self.assertEqual('403', resp_dict['status'])
        self.assertEqual('No file specified.', resp_dict['message'])

    def test_post_fails_with_malformed_tar_gz_file(self):
        blob_key = self._store_in_blobstore('abc')
        app_context = sites.get_app_context_for_namespace('ns_test')
        job = xblock_module.XBlockArchiveJob(app_context, blob_key=blob_key)
        resp_dict = job.run()
        self.assertFalse(resp_dict['success'])
        self.assertIn('Unable to read the archive file', resp_dict['message'])

    def _store_in_blobstore(self, data):
        file_name = files.blobstore.create(mime_type='application/octet-stream')
        with files.open(file_name, 'a') as f:
            f.write(data)
        files.finalize(file_name)
        return files.blobstore.get_blob_key(file_name)

    def _base_import_archive(self, archive_name=None, dry_run=False):
        archive_name = archive_name or 'functional_tests.tar.gz'
        archive = os.path.join(
            os.path.dirname(__file__), 'resources', archive_name)
        blob_key = self._store_in_blobstore(open(archive).read())

        app_context = sites.get_app_context_for_namespace('ns_test')
        job = xblock_module.XBlockArchiveJob(
            app_context, blob_key=blob_key, dry_run=dry_run)
        resp_dict = job.run()
        self.assertTrue(resp_dict['success'])
        return resp_dict

    def _import_archive(self, archive_name=None):
        resp_dict = self._base_import_archive(archive_name, dry_run=False)
        self.assertIn('Upload successfully imported', resp_dict['message'])
        return resp_dict

    def _import_dry_run_archive(self, archive_name=None):
        resp_dict = self._base_import_archive(archive_name, dry_run=True)
        self.assertIn('Upload successfully validated', resp_dict['message'])
        return resp_dict

    def _get_root_usage(self, body):
        match = re.compile(r'<xblock root_id="(\d+)"></xblock>').match(body)
        self.assertIsNotNone(match)
        root_usage_id = match.group(1)
        return xblock_module.RootUsageDao.load(root_usage_id)

    def _confirm_base_course_structure(self):
        rt = xblock_module.Runtime(MockHandler())

        # Confirm that the course has been imported correctly
        app_context = sites.get_all_courses()[0]
        course = courses.Course(None, app_context=app_context)
        units = course.get_units()

        # Expect the course to have two units
        self.assertEqual(2, len(units))
        unit1, unit2 = units
        self.assertEqual('Section 1', unit1.title)
        self.assertEqual('Section 2', unit2.title)
        self.assertEqual(
            '688fe994cb234bf48eb96c84aea018b5',
            unit1.properties['xblock.usage_id'])
        self.assertEqual(
            '094732b6779740029b88d8db4efce83b',
            unit2.properties['xblock.usage_id'])

        # The first unit has two lessons, the second unit no lessons
        unit1_lessons = course.get_lessons(unit1.unit_id)
        self.assertEqual(2, len(unit1_lessons))
        unit2_lessons = course.get_lessons(unit2.unit_id)
        self.assertEqual(0, len(unit2_lessons))

        # Tests for Unit 1, Lesson 1:

        lesson = unit1_lessons[0]

        self.assertEqual('Subsection 1.1', lesson.title)
        root_usage = self._get_root_usage(lesson.objectives)
        self.assertEqual(
            'Unit 1, Lesson 1: Subsection 1.1', root_usage.description)

        # The lesson has a sequence of two verticals
        block = rt.get_block(root_usage.usage_id)
        self.assertEqual('sequential', block.xml_element_name())
        self.assertEqual(2, len(block.children))

        # The usage ID is set from the archive file
        self.assertEqual(
            '974d5439622e4012bd28998efa15e02d', block.scope_ids.usage_id)

        # The first vertical has a single HTML block with some text
        child = rt.get_block(block.children[0])
        self.assertEqual('vertical', child.xml_element_name())
        self.assertEqual(1, len(child.children))
        grandchild = rt.get_block(child.children[0])
        self.assertEqual('html', grandchild.xml_element_name())
        self.assertIn('Some text', grandchild.content)

        # The second vertical has two components
        child = rt.get_block(block.children[1])
        self.assertEqual('vertical', child.xml_element_name())
        self.assertEqual(2, len(child.children))
        # First, an HTML block with an image
        grandchild = rt.get_block(child.children[0])
        self.assertEqual('html', grandchild.xml_element_name())
        self.assertIn(
            '<img src="assets/img/static/test.png">', grandchild.content)
        # Second, a YouTube video
        grandchild = rt.get_block(child.children[1])
        self.assertEqual('video', grandchild.xml_element_name())
        self.assertIn('Kdg2drcUjYI', grandchild.youtube_id_1_0)

        # Tests for Unit 1, Lesson 2:

        lesson = unit1_lessons[1]
        root_usage = self._get_root_usage(lesson.objectives)
        self.assertEqual(
            'Unit 1, Lesson 2: Subsection 1.2', root_usage.description)

        # The lesson has a sequence of one vertical
        block = rt.get_block(root_usage.usage_id)
        self.assertEqual('sequential', block.xml_element_name())
        self.assertEqual(1, len(block.children))

        # The vertical has a single HTML block with some text
        child = rt.get_block(block.children[0])
        self.assertEqual('vertical', child.xml_element_name())
        self.assertEqual(1, len(child.children))
        grandchild = rt.get_block(child.children[0])
        self.assertEqual('html', grandchild.xml_element_name())
        self.assertIn('Unit 3 text', grandchild.content)

        # The image resources bundled in the course are installed
        fs = app_context.fs.impl
        path = fs.physical_to_logical('assets/img/static/test.png')
        self.assertTrue(fs.isfile(path))
        image = fs.get(path).read()
        self.assertEqual(5861, len(image))

    def test_good_course_archive(self):
        # Upload a vaid course archive
        self._import_archive()
        self._confirm_base_course_structure()

    def test_import_then_merge(self):
        rt = xblock_module.Runtime(MockHandler())

        # Import the course then merge in some changes
        self._import_archive(archive_name='functional_tests.tar.gz')
        self._confirm_base_course_structure()
        self._import_archive(archive_name='functional_tests_merge.tar.gz')

        app_context = sites.get_all_courses()[0]
        course = courses.Course(None, app_context=app_context)
        units = course.get_units()

        # Confirm the unit structure; Unit 1 has changed names
        self.assertEqual(2, len(units))
        unit1, unit2 = units
        self.assertEqual('Section One', unit1.title)  # changed
        self.assertEqual('Section 2', unit2.title)
        self.assertEqual(
            '688fe994cb234bf48eb96c84aea018b5',
            unit1.properties['xblock.usage_id'])
        self.assertEqual(
            '094732b6779740029b88d8db4efce83b',
            unit2.properties['xblock.usage_id'])

        # Both units now have one lesson each
        unit1_lessons = course.get_lessons(unit1.unit_id)
        self.assertEqual(1, len(unit1_lessons))
        unit2_lessons = course.get_lessons(unit2.unit_id)
        self.assertEqual(1, len(unit2_lessons))

        # Tests for Unit 1, Lesson 1:

        lesson = unit1_lessons[0]

        self.assertEqual('Subsection One point one', lesson.title)  # changed
        root_usage = self._get_root_usage(lesson.objectives)
        self.assertEqual(
            'Unit 1, Lesson 1: Subsection One point one',  # changed
            root_usage.description)

        # The lesson has a sequence of two verticals
        block = rt.get_block(root_usage.usage_id)
        self.assertEqual('sequential', block.xml_element_name())
        self.assertEqual(2, len(block.children))

        # The usage ID is unchanged
        self.assertEqual(
            '974d5439622e4012bd28998efa15e02d', block.scope_ids.usage_id)

        # The first vertical has a single HTML block with some text
        child = rt.get_block(block.children[0])
        self.assertEqual('vertical', child.xml_element_name())
        self.assertEqual(1, len(child.children))
        grandchild = rt.get_block(child.children[0])
        self.assertEqual('html', grandchild.xml_element_name())
        self.assertIn('Some modified text', grandchild.content)  # changed

        # The second vertical has two components
        child = rt.get_block(block.children[1])
        self.assertEqual('vertical', child.xml_element_name())
        self.assertEqual(2, len(child.children))
        # First, an HTML block with an image
        grandchild = rt.get_block(child.children[0])
        self.assertEqual('html', grandchild.xml_element_name())
        self.assertIn(
            '<img src="assets/img/static/test.png">', grandchild.content)
        # Second, a YouTube video
        grandchild = rt.get_block(child.children[1])
        self.assertEqual('video', grandchild.xml_element_name())
        self.assertIn('Kdg2drcUjYI', grandchild.youtube_id_1_0)

        # Tests for Unit 2, Lesson 1 (which is all new)

        lesson = unit2_lessons[0]

        self.assertEqual('Subsection 2.1', lesson.title)  # changed
        root_usage = self._get_root_usage(lesson.objectives)
        self.assertEqual(
            'Unit 2, Lesson 1: Subsection 2.1', root_usage.description)

        # The lesson has a sequential with one vertical
        block = rt.get_block(root_usage.usage_id)
        self.assertEqual('sequential', block.xml_element_name())
        self.assertEqual(1, len(block.children))

        # The vertical has a single HTML block with some text
        child = rt.get_block(block.children[0])
        self.assertEqual('vertical', child.xml_element_name())
        self.assertEqual(1, len(child.children))
        grandchild = rt.get_block(child.children[0])
        self.assertEqual('html', grandchild.xml_element_name())
        self.assertIn('Text for Subsection 2.1', grandchild.content)

    def test_import_then_merge_journaling(self):
        self._import_archive(archive_name='functional_tests.tar.gz')
        resp_dict = self._import_dry_run_archive(
            archive_name='functional_tests_merge.tar.gz')
        expected_message = """Upload successfully validated:
Updating file '/assets/img/static/test.png'
Update unit title from 'Section 1' to 'Section One'
Update lesson title from 'Subsection 1.1' to 'Subsection One point one'
XBlock content updated in 'Subsection One point one' (974d5439622e4012bd28998efa15e02d)
Delete lesson 'Subsection 1.2'
Update unit title from 'Section 2' to 'Section 2'
Create lesson 'Subsection 2.1'
XBlock content inserted in 'Subsection 2.1' (4d005fc5b85f436cb029d8b0942b4662)"""
        self.assertEqual(expected_message, resp_dict['message'])

    def test_merge_does_not_affect_non_imported_xblocks(self):
        # Insert XBlock content menually
        xsrf_token = utils.XsrfTokenManager.create_xsrf_token(
            xblock_module.XBlockEditorRESTHandler.XSRF_TOKEN)
        response = self.put(
            'rest/xblock',
            XBlockEditorRESTHandlerTestCase.get_request(xsrf_token))
        resp_dict = transforms.loads(response.body)
        self.assertEqual(200, resp_dict['status'])
        payload = transforms.loads(resp_dict['payload'])
        root_usage_id = payload['key']

        # Now import an archive and merge in another
        self._import_archive(archive_name='functional_tests.tar.gz')
        self._import_archive(archive_name='functional_tests_merge.tar.gz')

        # Confirm that the original XBlock content is unchanged
        root_usage = xblock_module.RootUsageDao.load(root_usage_id)
        block = xblock_module.Runtime(
            MockHandler()).get_block(root_usage.usage_id)
        self.assertEqual('html', block.xml_element_name())
        self.assertEqual('test html', block.content)

    def test_dry_run_with_good_course_archive(self):
        # Upload a vaid course archive
        resp_dict = self._import_dry_run_archive()

        self.assertIn('Upload successfully validated', resp_dict['message'])

        # Confirm that no course content was installed
        app_context = sites.get_all_courses()[0]
        course = courses.Course(None, app_context=app_context)
        self.assertEqual(0, len(course.get_units()))
        self.assertEqual(0, len(course.get_lessons_for_all_units()))

        # Confirm no XBlock content installed
        self.assertEqual(0, len(xblock_module.RootUsageDao.get_all()))
        self.assertEqual(0, len(dbmodels.DefinitionEntity.all().fetch(1000)))
        self.assertEqual(0, len(dbmodels.UsageEntity.all().fetch(1000)))
        self.assertEqual(0, len(dbmodels.KeyValueEntity.all().fetch(1000)))

        # Confirm no files were installed
        fs = app_context.fs.impl
        self.assertEqual(0, len(fs.list(fs.physical_to_logical(''))))

    def test_import_appends_new_units(self):
        app_context = sites.get_all_courses()[0]
        course = courses.Course(None, app_context=app_context)
        unit = course.add_unit()
        unit.title = 'test'
        course.save()
        assert 1 == len(course.get_units())

        self._import_archive()

        app_context = sites.get_all_courses()[0]
        course = courses.Course(None, app_context=app_context)
        assert 3 == len(course.get_units())
        assert course.get_units()[0].title == 'test'
        assert not course.get_units()[0].properties

    def test_import_updates_existing_units(self):
        app_context = sites.get_all_courses()[0]
        course = courses.Course(None, app_context=app_context)
        unit = course.add_unit()
        unit.title = 'test'
        unit.properties['xblock.usage_id'] = '688fe994cb234bf48eb96c84aea018b5'
        course.save()

        self._import_archive()

        app_context = sites.get_all_courses()[0]
        course = courses.Course(None, app_context=app_context)
        assert 2 == len(course.get_units())
        assert course.get_units()[0].title == 'Section 1'

    def test_import_removes_orphan_units(self):
        app_context = sites.get_all_courses()[0]
        course = courses.Course(None, app_context=app_context)
        unit = course.add_unit()
        unit.title = 'test'
        unit.properties['xblock.usage_id'] = 'non_existent_usage_id'
        course.save()
        assert 1 == len(course.get_units())

        self._import_archive()

        app_context = sites.get_all_courses()[0]
        course = courses.Course(None, app_context=app_context)
        assert 2 == len(course.get_units())
        self.assertEqual(
            '688fe994cb234bf48eb96c84aea018b5',
            course.get_units()[0].properties['xblock.usage_id'])
        self.assertEqual(
            '094732b6779740029b88d8db4efce83b',
            course.get_units()[1].properties['xblock.usage_id'])

    def _make_lesson_for_existing_unit(self):
        app_context = sites.get_all_courses()[0]
        course = courses.Course(None, app_context=app_context)
        unit = course.add_unit()
        unit.properties['xblock.usage_id'] = '688fe994cb234bf48eb96c84aea018b5'
        lesson = course.add_lesson(unit)
        return course, lesson

    def test_import_appends_new_lessons(self):
        course, lesson = self._make_lesson_for_existing_unit()
        lesson.title = 'test'
        course.save()

        self._import_archive()

        app_context = sites.get_all_courses()[0]
        course = courses.Course(None, app_context=app_context)
        unit = course.get_units()[0]
        assert 3 == len(course.get_lessons(unit.unit_id))
        assert 'test' == course.get_lessons(unit.unit_id)[0].title
        assert 'Subsection 1.1' == course.get_lessons(unit.unit_id)[1].title

    def test_import_updates_existing_lessons(self):
        course, lesson = self._make_lesson_for_existing_unit()
        lesson.title = 'test'
        lesson.properties[
            'xblock.usage_id'] = '974d5439622e4012bd28998efa15e02d'
        course.save()

        self._import_archive()

        app_context = sites.get_all_courses()[0]
        course = courses.Course(None, app_context=app_context)
        unit = course.get_units()[0]
        assert 2 == len(course.get_lessons(unit.unit_id))
        assert 'Subsection 1.1' == course.get_lessons(unit.unit_id)[0].title

    def test_import_removes_orphan_lessons(self):
        course, lesson = self._make_lesson_for_existing_unit()
        lesson.title = 'test'
        lesson.properties['xblock.usage_id'] = 'non_existent_usage_id'
        course.save()

        self._import_archive()

        app_context = sites.get_all_courses()[0]
        course = courses.Course(None, app_context=app_context)
        unit = course.get_units()[0]
        assert 2 == len(course.get_lessons(unit.unit_id))


class ImporterTestCase(TestBase):
    """Functional tests for the XBlock archive importer."""

    # The happy case is exercised end-to-end by
    # XBlockArchiveRESTHandlerTestCase.test_good_course_archive and so the
    # purpose of this class is only to test the edge-case handling of the
    # importer.

    class MockArchive(object):
        class MockMember(object):
            def __init__(self, name=None, isdir=False, size=0):
                self.name = name
                self._isdir = isdir
                self.size = size

            def isdir(self):
                return self._isdir

            def isfile(self):
                return not self._isdir

        def __init__(self):
            self.course_xml = '<course/>'
            self.members = [
                self.MockMember('root', isdir=True),
                self.MockMember('root/course.xml'),
                self.MockMember('root/static', isdir=True)]

        def getmembers(self):
            return self.members

        def extractfile(self, path):
            if path == 'root/course.xml':
                return StringIO(self.course_xml)
            else:
                return StringIO('file_data')

    class MockCourse(object):

        def get_units(self):
            return []

    class MockFileSystem(object):
        def __init__(self):
            self.last_put = None
            self.last_filedata_list = None
            self.wait_and_finalize_called = False

        def physical_to_logical(self, path):
            return path

        def isfile(self, unused_path):
            return False

        def put(self, path, unused_data):
            self.last_put = path

        def put_multi_async(self, filedata_list):
            self.last_filedata_list = filedata_list

            def wait_and_finalize():
                self.wait_and_finalize_called = True
            return wait_and_finalize

    def setUp(self):
        super(ImporterTestCase, self).setUp()
        self.archive = self.MockArchive()
        self.course = self.MockCourse()
        self.fs = self.MockFileSystem()
        self.rt = xblock_module.Runtime(MockHandler())

    def _new_importer(self):
        return xblock_module.Importer(
            self.archive, self.course, self.fs, self.rt)

    def test_base_name(self):
        self.importer = self._new_importer()
        self.assertEqual('root', self.importer.base)

    def test_validate_requires_course_element(self):
        self.archive.course_xml = '<not_a_course_element/>'
        self.importer = self._new_importer()
        self.importer.parse()

        errors = self.importer.validate()
        self.assertEqual(1, len(errors))
        self.assertIn('no root course tag', errors[0])

    def test_validate_requires_all_content_in_chapters(self):
        self.archive.course_xml = '<course><vertical/></course>'
        self.importer = self._new_importer()
        self.importer.parse()

        errors = self.importer.validate()
        self.assertEqual(1, len(errors))
        self.assertIn('content must be in chapters', errors[0])

    def test_validate_requires_all_content_in_sequentials(self):
        self.archive.course_xml = (
            '<course><chapter><vertical/></chapter></course>')
        self.importer = self._new_importer()
        self.importer.parse()

        errors = self.importer.validate()
        self.assertEqual(1, len(errors))
        self.assertIn('Chapters may only contain sequentials', errors[0])

    def test_overwrite_duplicate_files(self):
        self.archive.members.append(
            self.MockArchive.MockMember('root/static/test.png'))

        def isfile(path):
            return path == '/assets/img/static/test.png'
        self.fs.isfile = isfile
        self.assertIsNone(self.fs.last_put)

        self.importer = self._new_importer()
        self.importer.parse()
        self.importer.do_import()
        self.assertTrue(self.fs.wait_and_finalize_called)
        fd_list = self.fs.last_filedata_list
        self.assertEquals(1, len(fd_list))
        self.assertEquals(2, len(fd_list[0]))
        self.assertEquals('/assets/img/static/test.png', fd_list[0][0])
        self.assertEquals('file_data', fd_list[0][1].read())

    def test_refuse_to_install_too_large_files(self):
        self.archive.members.append(self.MockArchive.MockMember(
            'root/static/test.png',
            size=xblock_module.MAX_ASSET_UPLOAD_SIZE_K * 1024 + 1))
        self.importer = self._new_importer()
        self.importer.parse()
        try:
            self.importer.do_import()
            self.fail('Expected BadImportException')
        except xblock_module.BadImportException as expected:
            self.assertIn('Cannot upload files bigger than', str(expected))


class XBlockTagTestCase(TestBase):
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


class XBlockResourceHandlerTestCase(TestBase):
    """Functional tests for the handler for XBlock resources."""

    def test_serves_xblock_workbench_resources(self):
        response = self.get(
            '/modules/xblock_module/xblock_resources/css/workbench.css')
        self.assertEqual(200, response.status_int)


class XBlockLocalResourceHandlerTestCase(TestBase):
    """Functional tests for the handler for XBlock local resources."""

    def test_serves_xblock_local_resources(self):
        response = self.get(
            'modules/xblock_module/xblock_local_resources/sequential/public/'
            'images/sequence/film.png')
        self.assertEqual(200, response.status_int)
        self.assertEqual('image/png', response.headers['Content-Type'])
