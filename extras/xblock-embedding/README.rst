XBlocks Embedded in Web Pages
=============================

A very lightweight demo of how XBlocks might be embedded in static web pages.

NOTE: This is NOT production code and is presented for illustrative
purposes only.

Running the example application
-------------------------------

To set up and run the application, execute:

::

  sh ./scripts/run_example.sh

The demo will now be running and can be reached on http://localhost:8080.


How to use it
-------------

Connect to http://localhost:8080. You will see a form which accepts XBlock XML.
Press submit and a link will be created at the bottom of the page. This links to
a view page which displays the XBlock embedded in the middle of some Lorem Ipsum
text.

The key take-away is that the view page consists only of static HTML, with
the new XBlock's usage id pasted in. The rendering of the XBlock is orchestrated
by the server-side JS library xblock_lib.js. The view page could equally well
be a 100% static HTML page with the usage id hard-coded in.
