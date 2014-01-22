var dryRunCheckbox = cb_global.form.inputs[1];
var warningShown = false;

dryRunCheckbox.setValue(true);
dryRunCheckbox.on('updated', function(value) {
  if (! value && ! warningShown) {
    var response = confirm('Proceed with caution!\n\n' +
        'This will replace existing course content with\n' +
        'the contents of the archive and cannot be undone.\n\n' +
        'Consider previewing the results of a dry run first.\n\n' +
        'Do you want to continue?');
    dryRunCheckbox.setValue(! response);
    warningShown = true;
  }
});
