var XBLOCK_LIB_URL =  ENVIRONMENT['BASE_URL'] + 'js/xblock_lib.js';
function addOnLoadEventListener(f) {
  // TODO(jorr): Make this support IE <= 8
  window.addEventListener('load', f);
}
function onLoadHandler() {
  console.log("This library will install xblocks");
  appendScriptToBody(ENVIRONMENT['JQUERY_URL']);
  appendScriptToBody(XBLOCK_LIB_URL);
}
function appendScriptToBody(scriptUri) {
  var scriptTag = document.createElement('script');
  scriptTag.setAttribute('src', scriptUri);
  scriptTag.async = false;
  document.body.appendChild(scriptTag);
}
addOnLoadEventListener(onLoadHandler);
