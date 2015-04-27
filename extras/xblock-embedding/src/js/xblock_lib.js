(function(jQuery) {
  var $ = jQuery;

  var LOGIN_SERVICE = ENVIRONMENT['BASE_URL'] + 'login_in_popup';
  var DISPLAY_XBLOCK = ENVIRONMENT['BASE_URL'] + 'display_xblock';

  var xblockIframes = [];
  var loginWindow;

  function maybeLogin() {
    if (ENVIRONMENT['IN_SESSION']) {
      loadXblocks();
    } else {
      loginWindow = window.open(LOGIN_SERVICE);
    }
  }
  function xblockUrl(usageId) {
    return DISPLAY_XBLOCK + '?' + $.param({'usage_id': usageId});
  }
  function loadXblocks() {
    // Replace each <xblock> tag with an iframe holding the xblock 
    $('xblock').replaceWith(function() {
      var iframe = $('<iframe/>')
          .attr('src', xblockUrl(this.getAttribute('usage-id')))
          .css({'border': 'none'})
          .get(0);
      xblockIframes.push(iframe);
      return iframe;
    });
  }

  function init() {
    // Receive postMessage events
    $(window).on('message', function(evt) {
      var sourceWindow = evt.originalEvent.source;
      var data = evt.originalEvent.data;
      switch (data.action) {
        case 'login':
          if (sourceWindow == loginWindow) {
            console.log(data.studentId);
            // We don't need the student id right now, but will for LTI
            loadXblocks();
          }
          break;
        case 'resize':
          $.each(xblockIframes, function(i, iframe) {
            if (iframe.contentWindow == sourceWindow) {
              $(iframe).width(data.width).height(data.height);
              return false;
            }
          });
          break;
      }
    });

    maybeLogin();
  }
  $(init);
})(jQuery.noConflict(true));
