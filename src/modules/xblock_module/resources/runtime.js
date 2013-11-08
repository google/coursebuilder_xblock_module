RuntimeProvider.versions[1].handlerUrl = function(block, handler_name) {
  return "modules/xblock_module/handler" +
    "?usage=" + $(block).data('usage') +
    "&handler=" + handler_name +
    "&xsrf_token=" + $(block).data('xsrf-token');
};
