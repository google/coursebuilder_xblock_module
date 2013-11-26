XBlock Module for Course Builder
================================

An add-on module for `Course Builder`_ which enables it to use edX_
XBlocks_ in course content.

.. _`Course Builder`: https://code.google.com/p/course-builder/
.. _edX: https://www.edx.org
.. _XBlocks: https://github.com/edx/XBlock


Running the example application locally
---------------------------------------

To get started, the XBlock module can be run inside Course Builder on a local
development server. To set up and run the application on common Linux
distributions, execute:

::

  sh ./scripts/run_example.sh

This will set up a copy of Course Builder in ``examples/`` with the XBlock
module installed, and will start the App Engine development server. If this
script cannot be run on your platform, follow the steps outlined in
`cbreadme.rst <cbreadme.rst>`_.


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


Adding the module to Course Builder
-----------------------------------

If you want to add the module to an existing copy of Course Builder, follow
the instructions in `cbreadme.rst <cbreadme.rst>`_.


Using XBlocks in Course Builder
-------------------------------

You can add XBlock content in XML form to the body of Course Builder lessons.
The following example describes the steps to add a snippet of HTML text and a
thumbs XBlock to a lesson:

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

      <vertical>
        <html>
          Vote up or down on the content...
        </html>
        <thumbs/>
      </vertical>

  7. Enter a description, such as "Sample XBlock content" and click Save, then
     Close.
  8. Next go to the course Outline tab and add a new unit and then a new lesson.
  9. Edit the lesson and use the Rich Text Editor for the lesson body.
  10. Click on the toolbox icon to embed a course component. Select
      "Embedded XBlocks" as the component type, and choose the description of
      the XBlock content you just added.
  11. Save your lesson and click close to return to the dashboard.
  12. Click on your lesson name to view the content as a student.


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

  4. You can now use the added XBlocks in your Course Builder installation.


Running the tests
-----------------

To run the tests on common Linux distributions, execute:

::

    sh ./scripts/tests.sh

If this script cannot be run on your platform, follow the steps in
`Running the example application locally`_
to set up a copy of Course Builder with the XBlock module installed.
Ensure that the following packages are on your ```PYTHONPATH``:

::

    examples/coursebuilder
    examples/webtest
    examples/google_appengine
    examples/google_appengine/lib/webob-1.2.3
    examples/google_appengine/lib/webapp2-2.5.2
    examples/google_appengine/lib/jinja2-2.6
    examples/google_appengine/lib/fancy_urllib

Then execute the tests with the following command:

::

    python -m unittest tests.xblock_module
