"use strict";

const page = document.body.dataset.page;
const eventPageState = {
  slug: null,
  data: null,
  session: null,
  availability: null,
  saveTimer: null,
  saving: false,
  painting: false,
  paintValue: "1",
  pointerId: null,
};

if (page === "create") {
  initializeCreatePage();
} else if (page === "event") {
  initializeEventPage();
}

function initializeCreatePage() {
  const form = document.querySelector("#event-form");
  const dateList = document.querySelector("#date-list");
  const addDateButton = document.querySelector("#add-date");
  const submitButton = document.querySelector("#create-event");
  const status = document.querySelector("#form-status");
  const timezone = document.querySelector("#timezone");

  timezone.value = resolvedTimezone();
  addDateRow(dateList, tomorrow());

  addDateButton.addEventListener("click", () => {
    addDateRow(dateList, "");
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearStatus(status);

    if (!form.reportValidity()) {
      return;
    }

    const dates = [...dateList.querySelectorAll('input[type="date"]')]
      .map((input) => input.value)
      .filter(Boolean);

    if (dates.length === 0) {
      setStatus(status, "Add at least one proposed date.", "error");
      return;
    }

    const startMinute = timeToMinute(document.querySelector("#start-time").value);
    const endMinute = timeToMinute(document.querySelector("#end-time").value);
    if (startMinute >= endMinute) {
      setStatus(status, "Daily end must be after the start time.", "error");
      return;
    }

    submitButton.disabled = true;
    submitButton.textContent = "Creating event…";

    try {
      const result = await requestJson("/api/events", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          name: document.querySelector("#event-name").value,
          schedule_kind: "dates",
          dates,
          day_start_minute: startMinute,
          day_end_minute: endMinute,
          slot_minutes: Number(document.querySelector("#slot-minutes").value),
          timezone: timezone.value,
        }),
      });
      window.location.assign(`/e/${encodeURIComponent(result.slug)}`);
    } catch (error) {
      setStatus(status, error.message, "error");
      submitButton.disabled = false;
      submitButton.textContent = "Create event";
    }
  });
}

function addDateRow(container, value) {
  const row = document.createElement("div");
  row.className = "date-row";

  const input = document.createElement("input");
  input.type = "date";
  input.name = "dates";
  input.value = value;
  input.required = true;
  input.setAttribute("aria-label", "Proposed date");

  const removeButton = document.createElement("button");
  removeButton.className = "button remove-date";
  removeButton.type = "button";
  removeButton.textContent = "Remove";
  removeButton.addEventListener("click", () => {
    if (container.children.length > 1) {
      row.remove();
    }
  });

  row.append(input, removeButton);
  container.append(row);
}

async function initializeEventPage() {
  const slug = eventSlug();
  const loading = document.querySelector("#event-loading");
  const content = document.querySelector("#event-content");
  const errorPanel = document.querySelector("#event-error");

  eventPageState.slug = slug;
  configureShareLink();
  configureJoinForm(slug);

  try {
    const eventData = await loadEvent(slug);
    eventPageState.data = eventData;
    renderEvent(eventData);
    restoreSession(slug, eventData);
    loading.hidden = true;
    content.hidden = false;
  } catch (error) {
    loading.hidden = true;
    errorPanel.hidden = false;
    document.querySelector("#event-error-message").textContent = error.message;
  }
}

async function loadEvent(slug) {
  return requestJson(`/api/events/${encodeURIComponent(slug)}`);
}

function renderEvent(data) {
  const event = data.event;
  document.title = `${event.name} · Huddle`;
  document.querySelector("#event-title").textContent = event.name;
  document.querySelector("#event-summary").textContent = [
    formatSchedule(event),
    `${minuteToTime(event.day_start_minute)}–${minuteToTime(event.day_end_minute)}`,
    `${event.slot_minutes}-minute slots`,
    event.timezone,
  ].join(" · ");

  const participantList = document.querySelector("#participant-list");
  participantList.replaceChildren();

  for (const participant of data.participants) {
    const item = document.createElement("li");
    const avatar = document.createElement("span");
    const name = document.createElement("span");
    avatar.className = "participant-avatar";
    avatar.textContent = participant.name.slice(0, 2).toLocaleUpperCase();
    name.textContent = participant.name;
    item.append(avatar, name);
    participantList.append(item);
  }

  document.querySelector("#participant-count").textContent = String(
    data.participants.length,
  );
  document.querySelector("#empty-participants").hidden =
    data.participants.length > 0;
}

function configureShareLink() {
  const shareLink = document.querySelector("#share-link");
  const copyButton = document.querySelector("#copy-link");
  const status = document.querySelector("#copy-status");
  shareLink.value = window.location.href;

  copyButton.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(shareLink.value);
      setStatus(status, "Link copied.", "success");
    } catch (_error) {
      shareLink.select();
      const copied = document.execCommand("copy");
      setStatus(
        status,
        copied ? "Link copied." : "Select and copy the link manually.",
        copied ? "success" : "error",
      );
    }
  });
}

function configureJoinForm(slug) {
  const form = document.querySelector("#join-form");
  const status = document.querySelector("#join-status");
  const submitButton = document.querySelector("#join-event");
  const clearSessionButton = document.querySelector("#clear-session");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearStatus(status);

    if (!form.reportValidity()) {
      return;
    }

    const name = document.querySelector("#participant-name").value.trim();
    const password = document.querySelector("#participant-password").value;
    submitButton.disabled = true;
    submitButton.textContent = "Joining…";

    try {
      const result = await requestJson(
        `/api/events/${encodeURIComponent(slug)}/participants`,
        {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            name,
            password: password || null,
          }),
        },
      );
      const session = {
        participant_id: result.participant_id,
        edit_token: result.edit_token,
        name,
      };
      localStorage.setItem(
        sessionKey(slug),
        JSON.stringify(session),
      );
      eventPageState.session = session;
      showSession(name);
      const refreshedEvent = await loadEvent(slug);
      eventPageState.data = refreshedEvent;
      renderEvent(refreshedEvent);
      showAvailabilityGrid(refreshedEvent, session);
    } catch (error) {
      setStatus(status, error.message, "error");
      submitButton.disabled = false;
      submitButton.textContent = "Join event";
    }
  });

  clearSessionButton.addEventListener("click", () => {
    clearTimeout(eventPageState.saveTimer);
    localStorage.removeItem(sessionKey(slug));
    eventPageState.session = null;
    eventPageState.availability = null;
    document.querySelector("#session-summary").hidden = true;
    form.hidden = false;
    form.reset();
    submitButton.disabled = false;
    submitButton.textContent = "Join event";
    document.querySelector("#availability-panel").hidden = true;
    document.querySelector("#availability-locked").hidden = false;
  });
}

function restoreSession(slug, eventData) {
  try {
    const session = JSON.parse(localStorage.getItem(sessionKey(slug)));
    if (
      session
      && Number.isInteger(session.participant_id)
      && typeof session.edit_token === "string"
      && typeof session.name === "string"
    ) {
      const participantExists = eventData.participants.some(
        (participant) => participant.id === session.participant_id,
      );
      if (participantExists) {
        eventPageState.session = session;
        showSession(session.name);
        showAvailabilityGrid(eventData, session);
        return;
      }
    }
  } catch (_error) {
    // Invalid local data is cleared below.
  }
  localStorage.removeItem(sessionKey(slug));
}

function showSession(name) {
  document.querySelector("#join-form").hidden = true;
  document.querySelector("#session-summary").hidden = false;
  document.querySelector("#session-description").textContent =
    `Signed in as ${name}. Your edit access is saved in this browser.`;
}

function showAvailabilityGrid(eventData, session) {
  const participant = eventData.participants.find(
    (eventParticipant) => eventParticipant.id === session.participant_id,
  );
  if (!participant) {
    return;
  }

  eventPageState.availability = [...participant.availability];
  document.querySelector("#availability-locked").hidden = true;
  document.querySelector("#availability-panel").hidden = false;
  setStatus(
    document.querySelector("#availability-status"),
    "All changes saved",
    "success",
  );

  const grid = document.querySelector("#availability-grid");
  renderAvailabilityGrid(grid, eventData.event);
  configureAvailabilityPainting(grid);
}

function renderAvailabilityGrid(grid, event) {
  const slotsPerDay =
    (event.day_end_minute - event.day_start_minute) / event.slot_minutes;
  grid.style.setProperty("--date-count", String(event.dates.length));
  grid.replaceChildren();

  const headerRow = document.createElement("div");
  headerRow.className = "availability-row";
  headerRow.setAttribute("role", "row");

  const corner = document.createElement("div");
  corner.className = "availability-corner";
  corner.setAttribute("role", "columnheader");
  corner.textContent = "Time";
  headerRow.append(corner);

  for (const date of event.dates) {
    const header = document.createElement("div");
    header.className = "availability-date";
    header.setAttribute("role", "columnheader");
    header.textContent = formatGridDate(event.schedule_kind, date);
    headerRow.append(header);
  }
  grid.append(headerRow);

  for (let slotInDay = 0; slotInDay < slotsPerDay; slotInDay += 1) {
    const row = document.createElement("div");
    row.className = "availability-row";
    row.setAttribute("role", "row");

    const minute =
      event.day_start_minute + slotInDay * event.slot_minutes;
    const timeLabel = document.createElement("div");
    timeLabel.className = "time-label";
    timeLabel.setAttribute("role", "rowheader");
    timeLabel.textContent = minuteToTime(minute);
    row.append(timeLabel);

    for (let dayIndex = 0; dayIndex < event.dates.length; dayIndex += 1) {
      const slotIndex = dayIndex * slotsPerDay + slotInDay;
      const cell = document.createElement("button");
      cell.className = "availability-cell";
      cell.type = "button";
      cell.dataset.slotIndex = String(slotIndex);
      cell.setAttribute("role", "gridcell");
      cell.setAttribute(
        "aria-label",
        `${formatGridDate(event.schedule_kind, event.dates[dayIndex])} at ${minuteToTime(minute)}`,
      );
      updateAvailabilityCell(cell, slotIndex);
      row.append(cell);
    }
    grid.append(row);
  }
}

function configureAvailabilityPainting(grid) {
  if (grid.dataset.paintingConfigured === "true") {
    return;
  }
  grid.dataset.paintingConfigured = "true";

  grid.addEventListener("pointerdown", (event) => {
    const cell = event.target.closest(".availability-cell");
    if (!cell) {
      return;
    }
    event.preventDefault();
    const slotIndex = Number(cell.dataset.slotIndex);
    eventPageState.painting = true;
    eventPageState.pointerId = event.pointerId;
    eventPageState.paintValue =
      eventPageState.availability[slotIndex] === "1" ? "0" : "1";
    grid.setPointerCapture(event.pointerId);
    paintAvailabilityCell(cell);
  });

  grid.addEventListener("pointermove", (event) => {
    if (
      !eventPageState.painting
      || event.pointerId !== eventPageState.pointerId
    ) {
      return;
    }
    event.preventDefault();
    const element = document.elementFromPoint(event.clientX, event.clientY);
    const cell = element?.closest(".availability-cell");
    if (cell && grid.contains(cell)) {
      paintAvailabilityCell(cell);
    }
  });

  const finishPainting = (event) => {
    if (event.pointerId === eventPageState.pointerId) {
      eventPageState.painting = false;
      eventPageState.pointerId = null;
    }
  };
  grid.addEventListener("pointerup", finishPainting);
  grid.addEventListener("pointercancel", finishPainting);

  grid.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") {
      return;
    }
    const cell = event.target.closest(".availability-cell");
    if (!cell) {
      return;
    }
    event.preventDefault();
    const slotIndex = Number(cell.dataset.slotIndex);
    eventPageState.paintValue =
      eventPageState.availability[slotIndex] === "1" ? "0" : "1";
    paintAvailabilityCell(cell);
  });
}

function paintAvailabilityCell(cell) {
  const slotIndex = Number(cell.dataset.slotIndex);
  if (eventPageState.availability[slotIndex] === eventPageState.paintValue) {
    return;
  }
  eventPageState.availability[slotIndex] = eventPageState.paintValue;
  updateAvailabilityCell(cell, slotIndex);
  scheduleAvailabilitySave();
}

function updateAvailabilityCell(cell, slotIndex) {
  const available = eventPageState.availability[slotIndex] === "1";
  cell.classList.toggle("is-available", available);
  cell.setAttribute("aria-selected", String(available));
  cell.title = available ? "Available" : "Unavailable";
}

function scheduleAvailabilitySave() {
  clearTimeout(eventPageState.saveTimer);
  setStatus(
    document.querySelector("#availability-status"),
    "Unsaved changes…",
    "",
  );
  eventPageState.saveTimer = setTimeout(saveAvailability, 400);
}

async function saveAvailability() {
  if (!eventPageState.session || !eventPageState.availability) {
    return;
  }
  if (eventPageState.saving) {
    clearTimeout(eventPageState.saveTimer);
    eventPageState.saveTimer = setTimeout(saveAvailability, 100);
    return;
  }

  const savedSession = eventPageState.session;
  const snapshot = eventPageState.availability.join("");
  const status = document.querySelector("#availability-status");
  eventPageState.saving = true;
  setStatus(status, "Saving…", "");

  try {
    await requestJson(
      (
        `/api/events/${encodeURIComponent(eventPageState.slug)}/participants/`
        + `${savedSession.participant_id}/availability`
      ),
      {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          "X-Edit-Token": savedSession.edit_token,
        },
        body: JSON.stringify({availability: snapshot}),
      },
    );
    if (eventPageState.session !== savedSession) {
      return;
    }
    if (eventPageState.availability.join("") === snapshot) {
      setStatus(status, "All changes saved", "success");
    } else {
      scheduleAvailabilitySave();
    }
  } catch (error) {
    setStatus(status, `Save failed: ${error.message}`, "error");
  } finally {
    eventPageState.saving = false;
  }
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(apiErrorMessage(data, response.status));
  }
  return data;
}

function apiErrorMessage(data, statusCode) {
  if (typeof data?.detail === "string") {
    return data.detail;
  }
  if (Array.isArray(data?.detail) && data.detail.length > 0) {
    return data.detail.map((item) => item.msg).join(" ");
  }
  return `Request failed (${statusCode}).`;
}

function formatSchedule(event) {
  if (event.schedule_kind === "weekdays") {
    return event.dates.join(", ");
  }
  return event.dates
    .map((value) => {
      const [year, month, day] = value.split("-").map(Number);
      return new Intl.DateTimeFormat(undefined, {
        month: "short",
        day: "numeric",
      }).format(new Date(year, month - 1, day));
    })
    .join(", ");
}

function formatGridDate(scheduleKind, value) {
  if (scheduleKind === "weekdays") {
    return value;
  }
  const [year, month, day] = value.split("-").map(Number);
  return new Intl.DateTimeFormat(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
  }).format(new Date(year, month - 1, day));
}

function timeToMinute(value) {
  const [hour, minute] = value.split(":").map(Number);
  return hour * 60 + minute;
}

function minuteToTime(value) {
  const hour = String(Math.floor(value / 60)).padStart(2, "0");
  const minute = String(value % 60).padStart(2, "0");
  return `${hour}:${minute}`;
}

function resolvedTimezone() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}

function tomorrow() {
  const value = new Date();
  value.setDate(value.getDate() + 1);
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function eventSlug() {
  return decodeURIComponent(window.location.pathname.split("/").filter(Boolean).at(-1));
}

function sessionKey(slug) {
  return `huddle:${slug}:session`;
}

function setStatus(element, message, state) {
  element.textContent = message;
  element.dataset.state = state;
}

function clearStatus(element) {
  element.textContent = "";
  delete element.dataset.state;
}
