// Light "Desk" / dark "Terminal" switch.
//
// Loaded as a *blocking classic script* in the head so the stored choice is on
// <html> before the first paint. Everything else on the site is an ES module,
// which would be deferred and produce a flash of the wrong theme; the CSP
// forbids inline script, so this cannot be three lines in the document.

(function () {
  var KEY = "qg-theme";
  var root = document.documentElement;

  function stored() {
    try {
      var value = localStorage.getItem(KEY);
      return value === "light" || value === "dark" ? value : null;
    } catch (error) {
      return null; // private mode, or site data blocked
    }
  }

  var choice = stored();
  if (choice) root.setAttribute("data-theme", choice);

  window.QGTheme = {
    // No attribute means "follow the operating system", so ask it.
    current: function () {
      return (
        root.getAttribute("data-theme") ||
        (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
      );
    },

    set: function (theme) {
      root.setAttribute("data-theme", theme);
      try {
        localStorage.setItem(KEY, theme);
      } catch (error) {
        /* nothing to do — the theme still applies for this page load */
      }
      document.dispatchEvent(new CustomEvent("qg:theme", { detail: theme }));
    },

    toggle: function () {
      this.set(this.current() === "dark" ? "light" : "dark");
    },
  };
})();
