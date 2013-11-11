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
# Common library shared by all shell scripts in this package.
#

# Force shell to fail on any errors.
set -e

GCB_GIT_URL=https://code.google.com/p/course-builder/
GCB_REPO_NAME=course-builder
GCB_GIT_REV=69e21ccfbbe3
GCB_ZIP=https://course-builder.googlecode.com/files/coursebuilder_20130814_214936.zip

XBLOCK_GIT_URL=https://github.com/edx/XBlock.git
XBLOCK_REPO_NAME=XBlock
XBLOCK_GIT_REV=2daa4e541c1613a703262c9dcd6be9c1928b1299

GAE_XBLOCK_LIB_GIT_URL=https://github.com/google/appengine_xblock_runtime.git
GAE_XBLOCK_LIB_REPO_NAME=appengine_xblock_runtime
GAE_XBLOCK_LIB_GIT_REV=42e8abded4582f09cc11f0b3d3b2d45eea9290bf

GAE_URL=http://googleappengine.googlecode.com/files/google_appengine_1.8.2.zip

clean_examples_folder() {
  cd examples
  rm -rf $GCB_REPO_NAME
  rm -rf coursebuilder
  rm -rf google_appengine
  rm -rf webtest
  cd ..
}

checkout_course_builder() {
  cd examples
  git clone $GCB_GIT_URL $GCB_REPO_NAME
  cd $GCB_REPO_NAME
  git checkout $GCB_GIT_REV

  # Patch GCB to run the XBlock module
  git apply ../../scripts/resources/module.patch
  cp -a ../../src/modules/xblock_module coursebuilder/modules

  # Install coursebuilder in examples/
  mv coursebuilder ..

  # Download the 3rd party libraries needed for run
  wget $GCB_ZIP -O coursebuilder.zip
  unzip coursebuilder.zip
  mv coursebuilder/lib ../coursebuilder

  cd ..
  rm -rf $GCB_REPO_NAME
  cd ..
}

checkout_xblock() {
  cd examples/coursebuilder/lib
  git clone $XBLOCK_GIT_URL $XBLOCK_REPO_NAME
  cd $XBLOCK_REPO_NAME
  git checkout $XBLOCK_GIT_REV
  python setup.py egg_info
  cd thumbs
  python setup.py egg_info
  cd ../../../../..
}

checkout_gae_xblock_lib() {
  cd examples/coursebuilder/lib
  git clone $GAE_XBLOCK_LIB_GIT_URL $GAE_XBLOCK_LIB_REPO_NAME
  cd $GAE_XBLOCK_LIB_REPO_NAME
  git checkout $GAE_XBLOCK_LIB_GIT_REV
  python setup.py egg_info
  cd ../../../..
}

require_course_builder() {
  if [ ! -d examples/coursebuilder ]; then
    checkout_course_builder
    checkout_xblock
    checkout_gae_xblock_lib
  fi
}

require_gae() {
  if [ ! -d examples/google_appengine ]; then
    cd examples
    wget $GAE_URL -O google_appengine.zip
    unzip google_appengine.zip
    rm google_appengine.zip
    cd ..
  fi
}

require_webtest() {
  if [ ! -d examples/webtest ]; then
    echo Installing webtest framework
    cd examples
    wget http://pypi.python.org/packages/source/W/WebTest/WebTest-1.4.2.zip -O webtest-download.zip
    unzip webtest-download.zip
    rm webtest-download.zip
    mv WebTest-1.4.2 webtest
    cd ..
  fi
}

install_requirements() {
  require_course_builder
  require_gae
  require_webtest
}

start_local_server() {
  install_requirements
  cd examples/coursebuilder
  ../google_appengine/dev_appserver.py .
  cd ..
}