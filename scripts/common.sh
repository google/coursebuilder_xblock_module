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
GCB_GIT_REV=1842c3c822bd
GCB_ZIP=http://releases.course-builder.googlecode.com/git/coursebuilder_1.6.0_20140221_144131.zip

XBLOCK_GIT_URL=https://github.com/edx/XBlock.git
XBLOCK_GIT_REV=de92d3bf798699a6bbd06b54012ef15934c41ac0

EDX_PLATFORM_GIT_URL=https://github.com/edx/edx-platform.git
EDX_PLATFORM_REPO_NAME=edx-platform
EDX_PLATFORM_REV=87aa71c4506c421a775c2cb732b4b813836c283c

GAE_XBLOCK_LIB_GIT_URL=https://github.com/google/appengine_xblock_runtime.git
GAE_XBLOCK_LIB_REPO_NAME=appengine_xblock_runtime
GAE_XBLOCK_LIB_GIT_REV=f0ef6fb8b6db01bdc15c10dd5858b4e77a58ee84

GAE_URL=http://googleappengine.googlecode.com/files/google_appengine_1.8.9.zip

clean_examples_folder() {
  cd examples
  rm -rf $GCB_REPO_NAME
  rm -rf coursebuilder
  rm -rf google_appengine
  rm -rf webtest
  rm -rf edx-platform
  rm -rf node
  rm -rf selenium
  rm -rf chromedriver
  cd ..
  rm -rf cb-xblocks-core/Course_Builder_Core_XBlocks.egg-info
}

checkout_course_builder() {
  cd examples
  git clone $GCB_GIT_URL $GCB_REPO_NAME
  cd $GCB_REPO_NAME
  git checkout $GCB_GIT_REV

  # Patch GCB to run the XBlock module
  git apply ../../scripts/resources/module.patch

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
  cd examples
  
  git clone $XBLOCK_GIT_URL XBlock
  cd XBlock
  git checkout $XBLOCK_GIT_REV
  python setup.py egg_info
  cd thumbs
  python setup.py egg_info
  cd ../..

  # Take only the parts of XBlock which are needed
  mkdir coursebuilder/lib/XBlock
  mv XBlock/XBlock.egg-info coursebuilder/lib/XBlock
  mv XBlock/xblock coursebuilder/lib/XBlock
  mv XBlock/thumbs coursebuilder/lib/XBlock
  mv XBlock/workbench coursebuilder/lib/XBlock
  rm -rf XBlock

  cd ..
}

checkout_gae_xblock_lib() {
  cd examples/coursebuilder/lib
  git clone $GAE_XBLOCK_LIB_GIT_URL $GAE_XBLOCK_LIB_REPO_NAME
  cd $GAE_XBLOCK_LIB_REPO_NAME
  git checkout $GAE_XBLOCK_LIB_GIT_REV
  python setup.py egg_info
  cd ../../../..
}

checkout_edx_platform() {
  cd examples
  git clone $EDX_PLATFORM_GIT_URL
  cd $EDX_PLATFORM_REPO_NAME
  git checkout $EDX_PLATFORM_REV
  cd ../..
}

cleanup_edx_platform() {
  rm -rf examples/edx-platform
}

copy_required_files_from_edx_platform() {
  src=examples/edx-platform
  dest=examples/coursebuilder/lib/edx-platform

  # Move core Capa libraries into CB lib folder
  mkdir -p $dest/common/lib
  mv $src/common/lib/calc/ $dest/common/lib
  mv $src/common/lib/capa/ $dest/common/lib
  mv $src/common/lib/chem/ $dest/common/lib
  mv $src/common/lib/xmodule/ $dest/common/lib

  edx_static=$src/common/static
  cb_static=$dest/common/static

  mkdir -p $cb_static/images
  mv $edx_static/images/correct-icon.png $cb_static/images
  mv $edx_static/images/incorrect-icon.png $cb_static/images
  mv $edx_static/images/unanswered-icon.png $cb_static/images
  mv $edx_static/images/spinner.gif $cb_static/images

  mkdir -p $cb_static/js/capa/src
  mv $edx_static/js/capa/src/formula_equation_preview.js $cb_static/js/capa/src

  mkdir -p $cb_static/js/vendor
  mv $edx_static/js/vendor/underscore-min.js $cb_static/js/vendor

  edx_templates=$src/lms/templates
  cb_templates=$dest/lms/templates
  mkdir -p $cb_templates
  mv $edx_templates/problem_ajax.html $edx_templates/problem.html $cb_templates
}

build_edx_coffeescript_files() {
  require_coffeescript
  coffee=examples/node/bin/coffee
  coffee_out=examples/coursebuilder/lib/edx-platform/common/static/coffee
  coffee_src=examples/coursebuilder/lib/edx-platform/common/lib/xmodule/xmodule/js/src

  mkdir -p $coffee_out
  $coffee --compile --output $coffee_out/capa/ $coffee_src/capa/display.coffee
  $coffee --compile --output $coffee_out/ $coffee_src/javascript_loader.coffee
}

install_capa() {
  checkout_edx_platform
  copy_required_files_from_edx_platform
  build_edx_coffeescript_files
  cleanup_edx_platform
}

install_cb_xblock_module() {
  cd examples/coursebuilder/modules
  ln -s ../../../src/modules/xblock_module
  cd ../../..
}

install_cb_xblock_lib() {
  cd examples/coursebuilder/lib
  ln -s ../../../cb-xblocks-core
  cd cb-xblocks-core
  python setup.py egg_info
  cd ../../../..
}

install_from_pypi() {
  url=$1
  base=`echo $url | sed 's/^.*\/\([^\/][^\/]*\)\.tar\.gz$/\1/'`
  echo $url
  echo $base

  cd examples/coursebuilder/lib
  wget $url
  tar xzf $base.tar.gz
  cd $base
  zip -r ../$base.zip .
  cd ..
  rm -rf $base $base.tar.gz
  cd ../../..
}

install_capa_deps() {
  cd examples/coursebuilder/lib
  ln -s ../../../capa_stubs
  cd ../../..

  downloads="\
    https://pypi.python.org/packages/source/B/BeautifulSoup/BeautifulSoup-3.2.1.tar.gz \
    https://pypi.python.org/packages/source/p/python-dateutil/python-dateutil-2.2.tar.gz \
    https://pypi.python.org/packages/source/M/Mako/Mako-0.9.0.tar.gz \
    https://pypi.python.org/packages/source/M/MarkupSafe/MarkupSafe-0.18.tar.gz \
    https://pypi.python.org/packages/source/P/PyYAML/PyYAML-3.10.tar.gz \
    https://pypi.python.org/packages/source/s/six/six-1.5.2.tar.gz"

  for url in $downloads
  do
    install_from_pypi $url
  done

  # Install version of nltk for GAE
  cd examples/coursebuilder/lib
  git clone https://github.com/rutherford/nltk-gae.git
  cd nltk-gae
  git checkout 9181f8991d0566e693f82d0bb0479219c3fc8768
  rm -rf .git
  zip -r ../nltk-gae.zip .
  cd ..
  rm -rf nltk-gae
  cd ../../..

  # Install MathJax
  cd examples/coursebuilder/lib
  git clone https://github.com/mathjax/MathJax.git
  cd MathJax
  git checkout f3aaf3a2a3e964df2770dc4aaaa9c87ce5f47e2c
  rm -rf .git
  zip -r ../MathJax-fonts.zip ./fonts
  zip -r ../MathJax.zip . -x fonts/\*
  cd ..
  rm -rf MathJax
  cd ../../..
}

require_course_builder() {
  if [ ! -d examples/coursebuilder ]; then
    checkout_course_builder
    checkout_xblock
    install_capa
    checkout_gae_xblock_lib
    install_cb_xblock_module
    install_cb_xblock_lib
    install_capa_deps
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

require_node() {
  if [ ! -d examples/node ]; then
    cd examples
    wget http://nodejs.org/dist/v0.10.24/node-v0.10.24-linux-x86.tar.gz -O node-download.tgz
    tar xzf node-download.tgz
    mv node-v0.10.24-linux-x86 node
    rm node-download.tgz
    cd ..
  fi
  PATH="`pwd`/examples/node/bin":$PATH
}

require_coffeescript() {
  require_node
  if [ ! -e examples/node/bin/coffee ]; then
    examples/node/bin/npm install -g coffee-script@1.6.1
  fi
}

require_selenium() {
  if [ ! -d examples/selenium ]; then
    cd examples
    wget https://pypi.python.org/packages/source/s/selenium/selenium-2.39.0.tar.gz -O selenium-download.tgz
    tar xzf selenium-download.tgz
    rm selenium-download.tgz
    mv selenium-2.39.0 selenium
    cd ..
  fi

  if [ ! -d examples/chromedriver ]; then
  cd examples
  wget http://chromedriver.storage.googleapis.com/2.8/chromedriver_linux64.zip -O chromedriver-download.zip
  unzip chromedriver-download.zip -d chromedriver
  chmod a+x chromedriver/chromedriver
  rm chromedriver-download.zip
  cd ..
fi
}

install_run_requirements() {
  require_course_builder
  require_gae
}

install_test_requirements() {
  install_run_requirements
  require_webtest
  require_selenium
}

start_local_server() {
  install_run_requirements
  cd examples/coursebuilder
  ../google_appengine/dev_appserver.py --datastore_consistency_policy=consistent --max_module_instances=1 $1 .
  cd ../..
}
