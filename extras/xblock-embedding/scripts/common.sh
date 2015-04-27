#
# author: jorr@google.com (John Orr)
#
# Common library shared by all shell scripts in this package.
#

XBLOCK_GIT_URL=https://github.com/edx/XBlock.git
XBLOCK_REPO_NAME=XBlock
XBLOCK_GIT_REV=2daa4e541c1613a703262c9dcd6be9c1928b1299

GAE_XBLOCK_LIB_GIT_URL=https://github.com/google/appengine_xblock_runtime.git
GAE_XBLOCK_LIB_REPO_NAME=appengine_xblock_runtime
GAE_XBLOCK_LIB_GIT_REV=42e8abded4582f09cc11f0b3d3b2d45eea9290bf

GAE_URL=http://googleappengine.googlecode.com/files/google_appengine_1.8.2.zip

# Force shell to fail on any errors.
set -e

clean_examples_folder() {
  cd examples
  rm -rf app
  cd ..
}

checkout_xblock() {
  cd examples/app/lib
  git clone $XBLOCK_GIT_URL $XBLOCK_REPO_NAME
  cd $XBLOCK_REPO_NAME
  git checkout $XBLOCK_GIT_REV
  python setup.py egg_info
  cd thumbs
  python setup.py egg_info
  cd ../../../../..
}

checkout_gae_xblock_lib() {
  cd examples/app/lib
  git clone $GAE_XBLOCK_LIB_GIT_URL $GAE_XBLOCK_LIB_REPO_NAME
  cd $GAE_XBLOCK_LIB_REPO_NAME
  git checkout $GAE_XBLOCK_LIB_GIT_REV
  python setup.py egg_info
  cd ../../../..
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

install_app() {
  if [ ! -d examples/app ]; then
    cp -a src examples/app
    mkdir examples/app/lib
    checkout_gae_xblock_lib
    checkout_xblock
  fi
}

install_requirements() {
  require_gae
  install_app
}

start_local_server() {
  install_requirements
  ./examples/google_appengine/dev_appserver.py examples/app
}