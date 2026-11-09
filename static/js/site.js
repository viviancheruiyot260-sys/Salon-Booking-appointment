(function () {
  "use strict";

  var nav = document.getElementById("site-nav");
  if (nav) {
    nav.querySelectorAll("a").forEach(function (link) {
      link.addEventListener("click", function () {
        if (!window.bootstrap || !window.bootstrap.Collapse) return;
        var instance = window.bootstrap.Collapse.getInstance(nav);
        if (instance) instance.hide();
      });
    });
  }

  var form = document.getElementById("booking-form");
  if (!form) return;

  var services = readJson("service-data", []);
  var hours = readJson("hours-data", {});
  var select = document.getElementById("id_service");
  var dateInput = document.getElementById("id_appointment_date");
  var notes = document.getElementById("id_notes");
  var notesCount = document.getElementById("notes-count");
  var summaryName = document.getElementById("summary-name");
  var summaryPrice = document.getElementById("summary-price");
  var summaryDuration = document.getElementById("summary-duration");
  var summaryCategory = document.getElementById("summary-category");
  var summaryEmpty = document.getElementById("summary-empty");
  var hoursHint = document.getElementById("hours-hint");

  function readJson(id, fallback) {
    var node = document.getElementById(id);
    if (!node) return fallback;
    try {
      return JSON.parse(node.textContent);
    } catch (error) {
      return fallback;
    }
  }

  function findService(id) {
    for (var index = 0; index < services.length; index += 1) {
      if (String(services[index].id) === String(id)) return services[index];
    }
    return null;
  }

  function showSummary(service) {
    if (!summaryName) return;
    var visible = Boolean(service);
    summaryName.hidden = !visible;
    summaryPrice.hidden = !visible;
    summaryDuration.hidden = !visible;
    summaryCategory.hidden = !visible;
    if (summaryEmpty) summaryEmpty.hidden = visible;
    if (!service) return;
    summaryCategory.textContent = service.category;
    summaryName.textContent = service.name;
    summaryPrice.textContent = service.price;
    summaryDuration.textContent = service.duration;
  }

  function updateHours() {
    if (!dateInput || !dateInput.value || !hoursHint) return;
    var parts = dateInput.value.split("-");
    if (parts.length !== 3) return;
    var day = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    if (Number.isNaN(day.getTime())) return;
    var pythonWeekday = (day.getDay() + 6) % 7;
    var info = hours[String(pythonWeekday)];
    if (info && info.label) hoursHint.textContent = info.label;
  }

  if (select) {
    select.addEventListener("change", function () {
      showSummary(findService(select.value));
    });
  }
  if (dateInput) {
    dateInput.addEventListener("change", updateHours);
    dateInput.addEventListener("input", updateHours);
  }
  updateHours();

  function updateCount() {
    if (!notes || !notesCount) return;
    notesCount.textContent = String(notes.value.length) + " / 500";
  }
  if (notes) {
    notes.addEventListener("input", updateCount);
    updateCount();
  }

  form.addEventListener("submit", function () {
    var button = document.getElementById("booking-submit");
    if (!button) return;
    window.setTimeout(function () {
      button.disabled = true;
      button.textContent = "Booking…";
    }, 0);
    window.setTimeout(function () {
      button.disabled = false;
      button.textContent = "Book appointment";
    }, 10000);
  });
})();
