/**
 * Based on Cookie Notice JS by Alessandro Benoit
 */


(function () {
  "use strict";

  const SM_WEB_COOKIE = 'sm_web_cookie_consent';

  const SM_WEB_STATUS = {
    ALLOWED: 'ALLOWED',
    DISALLOWED: 'DISALLOWED',
    UNKNOWN: 'UNKNOWN'
  };

  const CONFIG = {
    'noticeText': 'BacLab uses cookies for better user experience.',

    'learnMoreLinkEnabled': true,
    'learnMoreLinkHref': '/terms',
    'learnMoreLinkText':'See our Privacy Policy.',
    'linkColor': document.currentScript.getAttribute('link_color') || 'rgb(0, 90, 162)',

    'buttonText': 'Accept',

    'cookieNoticePosition': 'bottom',

    'buttonBgColor': document.currentScript.getAttribute('button_bg_color') || 'rgb(0, 90, 162)',
    'buttonTextColor': document.currentScript.getAttribute('button_text_color') || 'rgb(255, 255, 255)',
    'noticeBgColor': document.currentScript.getAttribute('background_color') || 'rgb(240, 240, 240)',
    'noticeTextColor': document.currentScript.getAttribute('text_color') || 'rgb(0, 0, 0)',

    'toggleButtonUnknown': 'Currently not opted in, click here to opt out explicitly',
    'toggleButtonOptedIn': 'Currently opted in to analytics, click here to opt out',
    'toggleButtonOptedOut': 'Currently opted out of analytics, click here to opt in',
  };

  function set_matomo_cookie(enabled) {
    const d = new Date();

    d.setTime(d.getTime() + (365 * 24 * 60 * 60 * 1000));
    document.cookie = SM_WEB_COOKIE + '=' + enabled + ';' +
                      'Path=/structman/;' +
                      'Expires=' + d.toUTCString() + ';' +
                      'SameSite=Strict';
  }

  function enable_matomo() {
    set_matomo_cookie(true);
  }

  function disable_matomo() {
     set_matomo_cookie(false);
  }

  function get_matomo_status() {
    const cookie = document.cookie.split(';').filter((item) => item.trim().startsWith(SM_WEB_COOKIE + '=')).at(0);

    if (cookie === undefined)
      return SM_WEB_STATUS.UNKNOWN;

    const status = cookie.split('=').at(1)?.trim() == 'true';

    if (status)
      return SM_WEB_STATUS.ALLOWED;
 
    return SM_WEB_STATUS.DISALLOWED;
  }

  /**
   * Create notice
   * @param message
   * @param bgColor
   * @param textColor
   * @param position
   * @returns {HTMLElement}
   */
  function createNotice(message, bgColor, textColor, position) {
    const notice = document.createElement('div');
    const noticeStyle = notice.style;

    notice.innerHTML = message + '&nbsp;';
    notice.setAttribute('id', 'cookieNotice');

    noticeStyle.position = 'fixed';

    if (position === 'top') {
      noticeStyle.top = '0';
    } else {
      noticeStyle.bottom = '0';
    }

    noticeStyle.left = '0';
    noticeStyle.right = '0';
    noticeStyle.background = bgColor;
    noticeStyle.color = textColor;
    noticeStyle["z-index"] = '999';
    noticeStyle.padding = '10px 5px';
    noticeStyle["text-align"] = 'center';
    noticeStyle["font-size"] = "13px";
    noticeStyle["line-height"] = "28px";

    return notice;
  }

    /**
     * Create dismiss button
     * @param message
     * @param buttonColor
     * @param buttonTextColor
     * @returns {HTMLElement}
     */
  function createDismissButton(message, buttonColor, buttonTextColor) {
    const dismissButton = document.createElement('a');
    const dismissButtonStyle = dismissButton.style;

    dismissButton.href = '#';
    dismissButton.innerHTML = message;
    dismissButton.className = 'confirm';

    dismissButtonStyle.background = buttonColor;
    dismissButtonStyle.color = buttonTextColor;
    dismissButtonStyle['text-decoration'] = 'none';
    dismissButtonStyle.display = 'inline-block';
    dismissButtonStyle.padding = '0 15px';
    dismissButtonStyle.margin = '0 0 0 10px';

    return dismissButton;
  }

  /**
   * Create dismiss button
   * @param learnMoreLinkText
   * @param learnMoreLinkHref
   * @param linkColor
   * @returns {HTMLElement}
   */
  function createLearnMoreLink(learnMoreLinkText, learnMoreLinkHref, linkColor) {
    const learnMoreLink = document.createElement('a');
    const learnMoreLinkStyle = learnMoreLink.style;

    learnMoreLink.href = learnMoreLinkHref;
    learnMoreLink.textContent = learnMoreLinkText;
    learnMoreLink.target = '_blank';
    learnMoreLink.className = 'learn-more';

    learnMoreLinkStyle.color = linkColor;
    learnMoreLinkStyle['text-decoration'] = 'none';
    learnMoreLinkStyle.display = 'inline';

    return learnMoreLink;
  }

  function refresh_toggle_button() {
    const toggleButton = document.getElementById('matomo-toggle-button');

    if (!toggleButton)
      return;

    const status = get_matomo_status();
    let text;
    let action;
    
    if (status === SM_WEB_STATUS.UNKNOWN) {
      text = CONFIG.toggleButtonUnknown;
      action = () => {
        const noticeDomElement = window.matomoNotice;
        disable_matomo();
        if (noticeDomElement)
          noticeDomElement.parentNode.removeChild(noticeDomElement);
      };
    }
    else if (status === SM_WEB_STATUS.ALLOWED) {
      text = CONFIG.toggleButtonOptedIn;
      action = disable_matomo;
    }
    else if (status === SM_WEB_STATUS.DISALLOWED) {
      text = CONFIG.toggleButtonOptedOut;
      action = enable_matomo;
    }
    
    toggleButton.innerText = text;
    toggleButton.onclick = () => {
      action();
      refresh_toggle_button();
    };
  }

  let noticeInstance;

  function matomo_notice() {
    if (noticeInstance !== undefined) {
      return;
    }

    noticeInstance = this;

    const status = get_matomo_status();

    if (status === SM_WEB_STATUS.ALLOWED) {
      _paq.push(['setConsentGiven']); 
      return;
    }
    else if (status === SM_WEB_STATUS.DISALLOWED) {
      return;
    }

    const notice = createNotice(CONFIG.noticeText,
                                CONFIG.noticeBgColor,
                                CONFIG.noticeTextColor,
                                CONFIG.cookieNoticePosition);

    const noticeDomElement = document.body.appendChild(notice);

    if (CONFIG.learnMoreLinkEnabled) {
      const learnMoreLink = createLearnMoreLink(CONFIG.learnMoreLinkText,
                                                CONFIG.learnMoreLinkHref,
                                                CONFIG.linkColor);

      noticeDomElement.appendChild(learnMoreLink);
    }

    const dismissButton = createDismissButton(CONFIG.buttonText,
                                              CONFIG.buttonBgColor,
                                              CONFIG.buttonTextColor);

    dismissButton.addEventListener('click', function (e) {
      e.preventDefault();
      enable_matomo();
      refresh_toggle_button();
      noticeDomElement.parentNode.removeChild(noticeDomElement);
    });

    noticeDomElement.appendChild(dismissButton);

    return noticeDomElement;
  };

  document.addEventListener('DOMContentLoaded', function () {
    if (!noticeInstance) {
      window.matomoNotice = matomo_notice();
      refresh_toggle_button();
    }
  });

}());
