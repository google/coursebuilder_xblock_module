function SequenceBlock(runtime, element) {
  element = $(element);
  var position = element.find("div.sequence_block").data("position") || 0;
  var lastTabIndex = element.find("li.nav_button").length - 1;
  var prevButton = $(element.find("li.prev").get(0));
  var nextButton = $(element.find("li.next").get(0));

  function display(index) {
    element.find("div.content > div").addClass("hidden");
    var contentDiv = element.find("div.content > div").get(index);
    if (contentDiv) {
      $(contentDiv).removeClass("hidden");
    }
    var navLi = element.find("ul.sequence_nav > li").get(index + 1);
    if (navLi) {
      element.find("ul.sequence_nav > li").removeClass('active')
      $(navLi).addClass('active');
    }
    prevButton.removeClass("disabled");
    nextButton.removeClass("disabled");
    if (position == 0) {
      prevButton.addClass("disabled");
    }
    if (position == lastTabIndex) {
      nextButton.addClass("disabled");
    }
    $.ajax({
        type: "POST",
        url: runtime.handlerUrl(element.get(0), 'on_select'),
        data: JSON.stringify({position: index})
    });
  }

  function bind() {
    element.find("li.nav_button").click(function(evt) {
      position = $(evt.target).data("index");
      display(position);
    });

    prevButton.click(function() {
      if (position > 0) {
        display(--position);
      }
    });

    nextButton.click(function() {
      if (position < lastTabIndex) {
        display(++position);
      }
    });
  }

  bind();
  display(position);
}
