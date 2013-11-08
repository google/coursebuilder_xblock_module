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

install_requirements

GAE_HOME=examples/google_appengine

PYTHONPATH=examples/coursebuilder:$PYTHONPATH
PYTHONPATH=examples/webtest:$PYTHONPATH
PYTHONPATH=$GAE_HOME:$PYTHONPATH
PYTHONPATH=$GAE_HOME/lib/webob-1.2.3:$PYTHONPATH
PYTHONPATH=$GAE_HOME/lib/webapp2-2.5.2:$PYTHONPATH
PYTHONPATH=$GAE_HOME/lib/jinja2-2.6:$PYTHONPATH
PYTHONPATH=$GAE_HOME/lib/fancy_urllib:$PYTHONPATH
export PYTHONPATH

python -m unittest tests.xblock_module
