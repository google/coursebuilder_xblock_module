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

"""Load tests for Course Builder XBlock support.

Basic usage is to run this from the command line, with options to select the
test type and the number of threads and iterations. Note however that there are
several setup steps required first, which are documented below.

For testing,

$ python tests/load_tests.py --iteration_count=10 \
    --thread_count=20 <test_name> https://myapp.appspot.com/load_test_course


The following tests can be run:

user_state: Set then get a student.ONE scoped variable with high load. Expect
all values to be stored and readable.

user_state_summary: Increment a student.ALL scoped counter many times. Expect
the final count to be equal to actual total.

content: Read a student.NONE scoped field many times. Expect read data to always
be accurate.


To prepare your app for load testing:

1. Start with a clean distribution and run the bundled tests to ensure that all
dependencies are properly installed:

$ sh ./scripts/clean.sh
$ sh ./scripts/tests.sh

2. Edit src/modules/xblock_module/xblock_module.py and add the following line to
XBLOCK_WHITELIST:

    'test_fields = test_xblocks.test_xblocks:TestFieldsBlock',

3. Edit examples/coursebuilder/appengine_config.py and add the following line to
THIRD_PARTY_LIBS:

    _Library('test-xblocks'),

4. Edit examples/coursebuilder/controllers/sites.py and change the value of
CAN_IMPERSONATE to True. WARNING: This should never be done on a non-testing
app, as it allows third parties to impersonate any user on that app.

5. Either deploy your Course Builder app to App Engine or run it locally with
the dev server.

6. Create a new empty course, e.g., https://myapp.appspot.com/load_test_course

7. Add an XBlock in the course Assets tab with the following XML:

<test_fields/>

8. Create a single unit in the course, having a single lesson in it. Use the
Dashboard lesson editor to add the XBlock you created to your lesson body.

9. Make the course, unit, and lesson public.
"""

__author__ = 'John Orr (jorr@google.com)'

import json
import urllib
from xml.etree import cElementTree

import argparse
import html5lib
import logging
from tests.integration.load_test import TaskThread, WebSession
import random
import time
import uuid


# command line arguments parser
PARSER = argparse.ArgumentParser()
PARSER.add_argument(
    '--thread_count',
    help='Number of concurrent threads for executing the test.',
    default=1, type=int)
PARSER.add_argument(
    '--iteration_count',
    help='Number of iterations for executing the test. Each thread of each '
    'iteration acts as a unique user with the uid equal to:'
    'start_uid + thread_count * iteration_index.',
    default=1, type=int)
PARSER.add_argument(
    '--startup_interval',
    help='Insert a random delay of between 0 and startup_interval seconds at the start of each thread.',
    default=0, type=int)
PARSER.add_argument(
    'test_type',
    help='The type of test to run. Allowed values are: "content", "user_state", "user_state_summary"',
    type=str)
PARSER.add_argument(
    'base_url',
    help='Base URL of the course you want to test, '
    'e.g., http://mycb.appspot.com/new_course',
    type=str)


class XBlockLoadTest(object):
    TEST_TYPE_NONE = -1
    TEST_TYPE_CONTENT = 0
    TEST_TYPE_USER_STATE = 1
    TEST_TYPE_USER_STATE_SUMMARY = 2

    def __init__(self, base_url, uid='', test_type=TEST_TYPE_NONE, startup_interval=0):
        self.uid = uid
        self.base_url = base_url
        self.test_type = test_type
        self.startup_interval = startup_interval

        # this is an impersonation identity for the actor thread
        self.email = 'load_test_bot_%s@example.com' % self.uid
        self.name = 'Load Test Bot #%s' % self.uid

        impersonate_header = {
            'email': self.email, 'user_id': u'impersonation-%s' % self.uid}
        self.session = WebSession(
            uid=uid,
            common_headers={'Gcb-Impersonate': json.dumps(impersonate_header)})
        self.html_parser = html5lib.HTMLParser(
            tree=html5lib.treebuilders.getTreeBuilder('etree', cElementTree),
            namespaceHTMLElements=False)

    def run(self):
        time.sleep(self.startup_interval * random.random())
        block_data = self.get_block_data()
        self.usage_id = block_data['usage_id']
        self.xsrf_token = block_data['xsrf_token']

        if self.test_type == self.TEST_TYPE_CONTENT:
            self.read_content_and_settintgs()
        elif self.test_type == self.TEST_TYPE_USER_STATE:
            self.set_and_confirm_user_state()
        elif self.test_type == self.TEST_TYPE_USER_STATE_SUMMARY:
            self.increment_user_state_summary()

    def get_block_data(self):
        """Get the test_xblock in a lesson page and read its displayed data."""

        def extract_field(node, field_class):
            return node.find('.//div[@class="%s"]' % field_class).text

        body = self.session.get('%s/unit' % self.base_url)
        root = self.html_parser.parse(body)
        xblock_root = root.find('.//div[@class="xblock"]')
        block_data = {}
        block_data['xsrf_token'] = xblock_root.attrib['data-xsrf-token']
        for item in (
                'usage_id', 'content', 'settings', 'user_state',
                'user_state_summary'):
            block_data[item] = extract_field(xblock_root, item)
        return block_data

    def post_to_handler(
            self, xsrf_token=None, usage_id=None, handler=None, post_dict=None):
        url = '%s/modules/xblock_module/handler?%s' % (
            self.base_url, urllib.urlencode({
                'handler': handler,
                'usage': usage_id,
                'xsrf_token': xsrf_token}))
        return self.session.post(url, post_dict)

    def set_user_state(self, value):
        response = self.post_to_handler(
            xsrf_token=self.xsrf_token,
            usage_id=self.usage_id,
            handler='set_user_state',
            post_dict={'value': value})
        response_dict = json.loads(response)
        assert response_dict == {"status": 'ok'}

    def confirm_field(self, name, value):
        block_data = self.get_block_data()
        assert block_data[name] == value

    def set_and_confirm_user_state(self):
        value = uuid.uuid4().hex
        self.set_user_state(value)
        self.confirm_field('user_state', value)

    def increment_user_state_summary(self):
        response = self.post_to_handler(
            xsrf_token=self.xsrf_token,
            usage_id=self.usage_id,
            handler='increment_user_state_summary',
            post_dict={})
        response_dict = json.loads(response)
        assert response_dict['status'] == 'ok'

    def read_content_and_settintgs(self):
        block_data = self.get_block_data()
        assert block_data['content'] == 'content_value'
        assert block_data['settings'] == 'settings_value'


def run_all(args):
    """Runs test scenario in multiple threads."""
    if args.thread_count < 1 or args.thread_count > 256:
        raise Exception('Please use between 1 and 256 threads.')

    test_type = ['content', 'user_state', 'user_state_summary'].index(args.test_type)

    start_time = time.time()
    logging.info('Started testing: %s', args.base_url)
    logging.info('Running tests for: %s' % args.test_type)
    logging.info('thread_count: %s', args.thread_count)
    logging.info('iteration_count: %s', args.iteration_count)

    if test_type == XBlockLoadTest.TEST_TYPE_USER_STATE_SUMMARY:
        block_data = XBlockLoadTest(args.base_url).get_block_data()
        logging.info('testing block usage_id: %s' % block_data['usage_id'])
        start_user_state_summary = int(block_data['user_state_summary'])
        logging.info('start user_state_summary value: %s' % start_user_state_summary)

    try:
        for iteration_index in xrange(0, args.iteration_count):
            logging.info('Started iteration: %s', iteration_index)
            tasks = []
            WebSession.PROGRESS_BATCH = args.thread_count
            for index in xrange(0, args.thread_count):
                uid = '%s-%s' % (iteration_index, index)
                test = XBlockLoadTest(
                    args.base_url, uid=uid, test_type=test_type,
                    startup_interval=args.startup_interval)
                task = TaskThread(
                    test.run, name='PeerReviewLoadTest-%s' % index)
                tasks.append(task)
            try:
                TaskThread.execute_task_list(tasks)
            except Exception as e:
                logging.info('Failed iteration: %s', iteration_index)
                raise e
    finally:
        WebSession.log_progress(force=True)

    if test_type == XBlockLoadTest.TEST_TYPE_USER_STATE_SUMMARY:
        block_data = XBlockLoadTest(args.base_url).get_block_data()
        final_user_state_summary = int(block_data['user_state_summary'])
        logging.info('expected increment count: %s' % (args.iteration_count * args.thread_count))
        logging.info('actual increment count: %s' % (final_user_state_summary - start_user_state_summary))
        logging.info('final user_state_summary value: %s' % final_user_state_summary)

    logging.info('Done! Duration (s): %s', time.time() - start_time)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run_all(PARSER.parse_args())
