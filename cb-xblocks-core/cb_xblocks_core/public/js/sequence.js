function SequenceBlock(runtime, element) {
  element = $(element);

  var GCB_NAV_PREV_HASH = '#cb-xblocks-core-nav-prev';
  var GCB_NAV_NEXT_HASH = '#cb-xblocks-core-nav-next';

  var gcbPrevButtonLabel = element.find(".button-labels > .prev").text();
  var gcbNextButtonLabel = element.find(".button-labels > .next").text();
  var gcbEndButtonLabel = element.find(".button-labels > .end").text();

  var gcbPrevButtonUri = $("div.gcb-prev-button > a").attr("href");
  var gcbNextButtonUri = $("div.gcb-next-button > a").attr("href");

  var position;
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

    if (index == 0 && gcbPrevButtonUri == 'course') {
      $("div.gcb-prev-button > a").css('display', 'none');
    } else {
      $("div.gcb-prev-button > a").css('display', '');
      $("div.gcb-prev-button > a").text(gcbPrevButtonLabel);
    }

    if (index == lastTabIndex && gcbNextButtonUri == 'course') {
      $("div.gcb-next-button > a").text(gcbEndButtonLabel);
    } else {
      $("div.gcb-next-button > a").text(gcbNextButtonLabel);
    }
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

    // If CB has omitted the Prev button, restore it
    if ($("div.gcb-prev-button > a").length == 0) {
      $("div.gcb-prev-button").html('<a href="course"></a>')
      gcbPrevButtonUri = 'course';
    }

    // Remove the HREF actions on the CB Prev and Next buttons
    $("div.gcb-prev-button > a, div.gcb-next-button > a")
        .attr('href', 'javascript:void(0)');

    $("div.gcb-prev-button > a").click(function() {
      if (position > 0) {
        // Since the buttons are at the bottom of the page, scroll to top
        $("body").scrollTop(0);
        display(--position);
      } else {
        window.location = gcbPrevButtonUri + GCB_NAV_PREV_HASH;
      }
    });

    $("div.gcb-next-button > a").click(function() {
      if (position < lastTabIndex) {
        // Since the buttons are at the bottom of the page, scroll to top
        $("body").scrollTop(0);
        display(++position);
      } else {
        window.location = gcbNextButtonUri + GCB_NAV_NEXT_HASH;
      }
    });
  }

  function initialDisplay() {
    if (window.location.hash == GCB_NAV_PREV_HASH) {
      position = lastTabIndex;
      window.location.hash = '';
    } else if (window.location.hash == GCB_NAV_NEXT_HASH) {
      position = 0;
      window.location.hash = '';
    } else {
      position = element.find("div.sequence_block").data("position") || 0;
    }

    display(position);
  }

  bind();
  initialDisplay();
}
