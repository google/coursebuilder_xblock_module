var pollerId;
var pollerUrl;
var feedbackDiv;
var loadingDiv;

function initPage() {
  var editor = Y.one('#formContainer');

  feedbackDiv = Y.Node.create('<div class="cb-oeditor-xblock-import-msg"/>');
  editor.appendChild(feedbackDiv);

  loadingDiv = Y.Node.create(
      '<div class="ajax-loading">' +
      '  <span class="ajax-loading-dot-one">.</span>' +
      '  <span class="ajax-loading-dot-two">.</span>' +
      '  <span class="ajax-loading-dot-three">.</span>' +
      '</div>');
  editor.appendChild(loadingDiv);
}

function bind() {
  //Update the form's save URL to point to the blobstore upload.
  cb_global.save_url = cb_global.original.upload_url;
  pollerUrl = cb_global.original.poller_url;

  cb_global.onSaveClick = onSaveClick;
  cb_global.onSaveComplete = onSaveComplete;
}

function onSaveClick() {
  hideOutput();
}

function onSaveComplete(payload) {
  // Disable buttons and show loading spinner while polling
  disableAllControlButtons(cb_global.form);
  showLoadingDiv();
  cb_global.save_url = payload.new_upload_url;
  pollerId = setInterval(poll, 2500);
}

function poll() {
  Y.io(pollerUrl, {
    method: 'GET',
    timeout : 15000,
    on: {
      success: onPollSuccess
    }
  });
}

function showLoadingDiv() {
  loadingDiv.setStyle('display', 'block');
}

function hideLoadingDiv() {
  loadingDiv.setStyle('display', 'none');
}

function onPollSuccess(id, response, args) {
  var json = parseJson(response.responseText);
  var payload = parseJson(json.payload);
  console.log(payload);
  if (payload.complete) {
    cbHideMsg();
    clearInterval(pollerId);
    showOutput(parseJson(payload.output));
    enableAllControlButtons(cb_global.form);
    hideLoadingDiv();
  }
}

function showOutput(output) {
  console.log(output);
  if (! output.success) {
    feedbackDiv.addClass('error');
  }
  feedbackDiv.setStyle('display', 'block');
  feedbackDiv.set('text', output.message);
}

function hideOutput() {
  feedbackDiv.setStyle('display', 'none');
  feedbackDiv.removeClass('error');
  feedbackDiv.set('text', '');
}

function init() {
  initPage();
  bind();
}

init();