var Collapsible = {
  setCollapsibles: function(el) {}
};

var Logger = {
  log: function(msg) {
    console && console.log && console.log(msg);
  }
};

var analytics = {
  track: function(msg, data) {
    gcbTagEventAudit && gcbTagEventAudit({
      event: 'xblock-problem',
      message: msg,
      data: data
    },
    'xblock-event');
  }
};

var update_schematics = function() {};

// Mock i18n method
var gettext = function(text) {
  return text;
};

$.postWithPrefix = function() {
  if (arguments.length == 2) {
    var url = arguments[0];
    var data = {};
    var callback = arguments[1];
  } else if (arguments.length == 3) {
    var url = arguments[0];
    var data = arguments[1];
    var callback = arguments[2];
  } else {
    throw 'postWithPrefix called with ' + arguments.length + ' arguments.'
  }
  var urlComponents = url.split('/');
  var usageId = urlComponents[0];
  var method = urlComponents[1];

  var element = $.postWithPrefix.elementByUsageId[usageId];
  var runtime = $.postWithPrefix.runtime;
  
  if (method) {
    $.ajax({
      type: 'POST', // XBlock JSON handler must listen on POST
      url: runtime.handlerUrl(element, method),
      data: data,
      success: callback
    });
  }
};
$.postWithPrefix.elementByUsageId = {};

var ProblemBlock = function(runtime, element) {
  $.postWithPrefix.runtime = runtime;
  $.postWithPrefix.elementByUsageId[$(element).data('usage')] = element;
  var problem = new Problem(element);
}
