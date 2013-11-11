Adding the Module to Course Builder
===================================

The easiest way to setup a copy of Course Builder with XBlock support is to
execute the shell script:

::

  sh ./scripts/run_example.sh

from the base folder. However in some cases you may want to install the module
by hand; for example if the scripts do not run on your platform, or if you are
installing the module into an existing customized copy of Course Builder.


Prepare a copy of Course Builder
--------------------------------

First you must obtain a copy of Course Builder. If you are making a new copy,
clone Course Builder from the repository:

::

  git clone https://code.google.com/p/course-builder/

If you are using an existing copy of Course Builder, you must merge in the
changes on the ``master`` branch, up to ``HEAD``. The exact steps involved will
depend on how you maintain your customized copy of Course Builder, but might be
along the following lines:

::

  git checkout my_course_builder_branch
  git pull origin master

It's likely that there will be some merge conflicts which will then need to be
resolved by hand.

If you cloned a fresh copy of Course Builder from the repositiory, you will also
need to grab copies of the third-party libraries used by Course Builder, as
these are not part of the Git repositiory. The easiest way to do this is to
download a copy of the Course Builder 1.5.1 zip file and copy them over.
Download

::

  https://course-builder.googlecode.com/files/coursebuilder_20130814_214936.zip

into a temporary folder and unzip. Copy all the files from the new
``coursebuilder/lib/`` into the ``lib/`` folder of your Course Builder
installation.


Install required libraries
--------------------------

Next go into the ``coursebuilder/lib/`` folder, and clone a copy of
edX's XBlock package:

::

  git clone https://github.com/edx/XBlock.git
  cd XBlock
  git checkout 2daa4e541c1613a703262c9dcd6be9c1928b1299

  python setup.py egg_info
  cd thumbs
  python setup.py egg_info

You will also need to install the XBlock Runtime Library for App Engine.
Go back to ``coursebuilder/lib/`` and clone that library too:

::

  git clone https://github.com/google/appengine_xblock_runtime.git
  cd appengine_xblock_runtime
  git checkout 42e8abded4582f09cc11f0b3d3b2d45eea9290bf


Install the XBlock module
-------------------------

Copy the folder ``src/modules/xblock_module/`` into your
``coursebuilder/modules/`` folder, so that you now have a folder
``coursebuilder/modules/xblock_module/``.


Patch Course Builder
--------------------

To activate the module and supply its dependencies you will need to edit three
files in Course Builder. All three are in the top-level Course Builder folder.

Edit ``app.yaml`` and add the following lines to the ``libraries`` section:

::

  - name: django
    version: "1.4"
  - name: lxml
    version: "2.3"

Edit ``appengine_config.py`` and locate the definition of the
``THIRD_PARTY_LIBS`` list (near ine 63). Add the following lines at the end of
the list:

 ::

  _Library('appengine_xblock_runtime'),
  _Library('XBlock'),
  _Library(os.path.join('XBlock', 'thumbs')),

Finally make two edits to ``main.py``. Add the following line to the bottom of
the imports section:

::

  import modules.xblock_module.xblock_module

Add the following line to the bottom of the section where modules are enabled
(about line 56):

::

  modules.xblock_module.xblock_module.register_module().enable()


Install the Google App Engine SDK
---------------------------------

Download:

::

  http://googleappengine.googlecode.com/files/google_appengine_1.8.2.zip

and unzip this.


Install packages required for testing
-------------------------------------

To run the tests you will also need to install WebTest. Download:

::

  http://pypi.python.org/packages/source/W/WebTest/WebTest-1.4.2.zip

and unzip this.


Starting the development server
-------------------------------

From the ``coursebuilder`` folder, execute:

::

  $APP_ENGINE_SDK/dev_appserver.py .
