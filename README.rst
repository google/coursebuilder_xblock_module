XBlock Module for Course Builder
================================

An add-on module for `Course Builder`_ which enables it to use edX_
XBlocks_ in course content.

.. _`Course Builder`: https://code.google.com/p/course-builder/
.. _edX: https://www.edx.org
.. _XBlocks: https://github.com/edx/XBlock


Requirements
------------

You will need a Bash environment to run the installation scripts. The scripts
use standard developments tools, including Python 2.7, ``git``, and
``zip``/``unzip``. In addition you must have the following Python packages
installed: ``setuptools 2.1.2``, ``lxml 2.3.2``, ``numpy 1.6.1``.


Running the example application locally
---------------------------------------

To get started, the XBlock module can be run inside Course Builder on a local
development server. To set up and run the application, execute:

::

  sh ./scripts/run_example.sh

This will set up a copy of Course Builder in ``examples/`` with the XBlock
module installed, and will start the App Engine development server. The script
accepts ``dev_appserver.py`` flags.


Running the example application on production App Engine
--------------------------------------------------------

To install on production App Engine, first follow the steps in
`Running the example application locally`_, to set up a copy of
Course Builder in ``examples/`` with the module installed.

Next, create a new application on App Engine (https://appengine.google.com/)
with a name that matches the application name in
``examples/coursebuilder/app.yaml`` (e.g. 'mycourse')

Deploy with the command:

::

  ./examples/google_appengine/appcfg.py update examples/coursebuilder


Using XBlocks in Course Builder
-------------------------------

You can add XBlock content in XML form to the body of Course Builder lessons.
The following example describes the steps to add a snippet of HTML text and a
video XBlock to a lesson:

  1. Log on to Course Builder as an administrator.
  2. `Create a new course <https://code.google.com/p/course-builder/wiki/CreateNewCourse>`_
     using the admin tab.
  3. Go to the new course's
     `Dashboard <https://code.google.com/p/course-builder/wiki/Dashboard>`_,
     and select Assets.
  4. Observe the list of assets includes a new XBlocks section.
  5. Click Add XBlock.
  6. Paste the following XML into the XBlock definition box:

    ::

      <sequential>
        <html>Some text</html>
        <video youtube_id_1_0="Kdg2drcUjYI"/>
      </sequential>

  7. Enter a description, such as "Sample XBlock content" and click Save, then
     Close.
  8. Next go to the course Outline tab and add a new unit and then a new lesson.
  9. Edit the lesson and use the Rich Text Editor for the lesson body.
  10. Click on the toolbox icon to embed a course component. Select
      "Embedded XBlocks" as the component type, and choose the description of
      the XBlock content you just added.
  11. Save your lesson and click Close to return to the dashboard.
  12. Click on your lesson name to view the content as a student.


Importing Courses from edX Studio
---------------------------------

You can import course content created in edX Studio. Not all content that can
be authored in Studio runs in Course Builder, but basic content including HTML,
videos, and multiple choice questions is supported. The following steps show
the process for importing a course from Studio:

  1. Create your course in Studio.
  2. In your Studio  course, select Tools > Export and save a copy of your
     course as a ``.tar.gz`` file.
  3. Log on to Course Builder as an administrator.
  4. `Create a new course <https://code.google.com/p/course-builder/wiki/CreateNewCourse>`_
     using the admin tab.
  5. Go to the new course's
     `Dashboard <https://code.google.com/p/course-builder/wiki/Dashboard>`_,
     and select Assets.
  6. Click the Import button in the XBlocks section.
  7. Click Choose File and open the ``.tar.gz`` file which you downloaded from
     Studio.
  8. If you only want to confirm that this content can be imported to Course
     Builder, without actually loading it, click the Dry Run box.
  9. Click Import.

After the import, Studio sections will correspond to Course Builder units, and
Studio subsections will correspond to Course Builder lessons. Resources such as
embedded images will be imported. There are also sample exported files which
you can try in ``tests/resources/``.


Adding new XBlocks
------------------

The following steps describe how to add new XBlocks so that they will be recognized
by the XBlock module. They assume that you have packaged the XBlocks in a folder
called ``my_xblocks`` which contains a ``setup.py`` file (similar to the thumbs XBlock
that is included with the standard XBlock library).

  1. Copy the ``my_xblocks`` folder into the ``lib/`` folder of your Course
     Builder installation, so that you have a ``lib/my_xblocks`` folder that
     contains a ``setup.py`` file.

  2. In a terminal, execute the commands

     ::

       cd my_xblocks
       python setup.py egg_info

  3. In Course Builder, edit ``appengine_config.py`` and locate the definition of
     the ``THIRD_PARTY_LIBS`` list (near line 63). Add the following line at the
     end of the list:

     ::

       _Library('my_xblocks')

  4. In Course Builder, edit ``src/modules/xblock_module/xblock_module.py``
     and locate the XBLOCK_WHITELIST list (new line 86). Add the line for your
     XBlock from your XBlock's ``setup.py`` file. E.g.,

     ::

       myblock = my_package.my_module:MyBlockClass

  5. You can now use the added XBlock in your Course Builder installation.

If you are developing an XBlock then the above steps need only be performed
once. Subsequent edits to your XBlock's code will be immediately available.


Running the tests
-----------------

To run the tests, execute:

::

    sh ./scripts/tests.sh
