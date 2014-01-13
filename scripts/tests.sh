#! /bin/bash
#
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
#
# author: jorr@google.com (John Orr)
#
# This script runs the tests on the package.
#

. scripts/common.sh

install_test_requirements

GAE_HOME=examples/google_appengine

PYTHONPATH=examples/coursebuilder:$PYTHONPATH
PYTHONPATH=examples/selenium/py:$PYTHONPATH
PYTHONPATH=examples/webtest:$PYTHONPATH
PYTHONPATH=$GAE_HOME:$PYTHONPATH
PYTHONPATH=$GAE_HOME/lib/webob-1.2.3:$PYTHONPATH
PYTHONPATH=$GAE_HOME/lib/webapp2-2.5.2:$PYTHONPATH
PYTHONPATH=$GAE_HOME/lib/jinja2-2.6:$PYTHONPATH
PYTHONPATH=$GAE_HOME/lib/fancy_urllib:$PYTHONPATH
export PYTHONPATH

PATH=examples/chromedriver:$PATH

export gcb_courses_config=5

python -m unittest tests.xblock_module

# Ensure that failed tests don't terminate script before the server is shut down
set +e

exec examples/google_appengine/dev_appserver.py $1 \
  --clear_datastore=yes \
  --datastore_consistency_policy=consistent \
  --max_module_instances=1 \
  --host localhost \
  --port 8081 \
  examples/coursebuilder &
cb_pid=$!

python -m unittest tests.integration_tests

echo "Killing server process $cb_pid..."
kill $cb_pid