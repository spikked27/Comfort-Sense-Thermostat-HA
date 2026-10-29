/* Browser regression checks with a fake HA boundary; never contacts a household. */
const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");

(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CONSOLE_BROWSER || undefined,
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1400 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const root = path.resolve(__dirname, "..");
  const source = fs.readFileSync(
    path.join(root, "custom_components/comfort_sense/frontend/comfort-sense.js"),
    "utf8",
  );
  const icon = fs.readFileSync(path.join(root, "custom_components/comfort_sense/brand/icon@2x.png"));
  const defaults = {
    name: "Upstairs",
    heater: "switch.heat",
    shadow: true,
    outdoor_sensor: "sensor.outside",
    home_sensor: "",
    comfort_temperature: 70,
    sleep_temperature: 65,
    away_temperature: 65,
    boost_temperature: 72,
    reaction_time: "medium",
    occupancy_margin: 30,
    room_buffer: 3.6,
    boost_minutes: 60,
    sleep_room: "bedroom",
    away_delay_minutes: 20,
    sensor_timeout_minutes: 180,
    min_on_seconds: 300,
    min_off_seconds: 300,
    pwm_seconds: 1200,
    max_temperature: 82.4,
    max_preheat_minutes: 240,
    fallback_heat_rate: 0.9,
    morning_enabled: true,
    alarm_sensors: ["sensor.phone_alarm"],
    alarm_owners: { "sensor.phone_alarm": "person.matt" },
    morning_target: 68,
    morning_source: "bedroom",
    morning_duration: 60,
    alarm_window_start: "03:00",
    alarm_window_end: "12:00",
    average_tuning_mode: "auto",
    average_kp: 0.2,
    average_ki: 0.000035,
    average_kd: 0,
    schedules: [],
    rooms: [
      {
        id: "bedroom",
        name: "Bedroom",
        temperature_sensors: ["sensor.bedroom"],
        occupancy_sensors: ["binary_sensor.bedroom"],
        tuning_mode: "auto",
        kp: 0.2,
        ki: 0.000035,
        kd: 0,
      },
      {
        id: "living",
        name: "Living Room",
        temperature_sensors: ["sensor.living"],
        occupancy_sensors: [],
        tuning_mode: "auto",
        kp: 0.2,
        ki: 0.000035,
        kd: 0,
      },
    ],
  };
  const entities = [
    ["switch.heat", "Upstairs heater", "unavailable", "", ""],
    ["sensor.bedroom", "Bedroom temperature", "69.1", "°F", "temperature"],
    ["sensor.living", "Living Room temperature", "66.7", "°F", "temperature"],
    ["sensor.new_room", "Study temperature", "68.2", "°F", "temperature"],
    ["sensor.power", "Furnace power", "320", "W", "power"],
    ["sensor.outside", "Outdoor temperature", "45", "°F", "temperature"],
    ["sensor.phone_alarm", "Matt’s next alarm", "2026-10-30T09:50:00Z", "", "timestamp"],
    ["person.matt", "Matt", "home", "", ""],
    ["binary_sensor.bedroom", "Bedroom presence", "on", "", "occupancy"],
    ["schedule.weekdays", "Weekday mornings", "off", "", ""],
  ].map(([entity_id, name, state, unit, device_class]) => ({ entity_id, name, state, unit, device_class }));
  const data = {
    unit: "°F",
    areas: [],
    entities,
    entries: [
      {
        entry_id: "upstairs",
        revision: "initial",
        name: "Upstairs",
        config: defaults,
        climate_entity: "climate.upstairs",
        issues: [
          {
            level: "error",
            title: "Heater disconnected",
            detail: "Heating control and learning are waiting for relay feedback.",
            tab: "equipment",
          },
          {
            level: "info",
            title: "Observation only",
            detail: "Shadow mode is on. Comfort Sense does not switch the heater.",
            tab: "equipment",
          },
        ],
        rooms: [
          {
            id: "bedroom",
            temperature: 69.1,
            occupancy: 100,
            active: true,
            learning: "Collecting: need at least 48 hours and 400 valid samples",
            learned: false,
          },
          {
            id: "living",
            temperature: 66.7,
            occupancy: 0,
            active: false,
            learning: "Waiting for observations",
            learned: false,
          },
        ],
        external_schedules: [
          {
            name: "Thermostat workday schedule",
            entity_id: "switch.schedule",
            days: ["mon", "tue", "wed", "thu", "fri"],
            timeslots: ["04:30 - 06:30"],
          },
        ],
        live: {
          mode: "heat",
          preset: "sleep",
          source: "Bedroom",
          reason: "Heater unavailable",
          temperature: 69.1,
          target: 65,
          demand: 0,
          observed: null,
          proposed: false,
          outdoor: 45,
          outdoor_compensation: { status: "Waiting for accepted model", coefficient: null, active: false },
          target_origin: "Sleep preset",
          morning: "Alarm connected",
          plans: [],
          average_learning: "Waiting for valid heating feedback",
        },
      },
    ],
  };
  await page.route("http://comfort.test/**", async (route) => {
    if (route.request().url().endsWith("icon.png"))
      return route.fulfill({ contentType: "image/png", body: icon });
    return route.fulfill({
      contentType: "text/html",
      body: '<html style="height:100%"><body style="margin:0;height:100%"><comfort-sense-panel></comfort-sense-panel></body></html>',
    });
  });
  await page.goto("http://comfort.test/");
  await page.addScriptTag({ content: source });
  await page.evaluate((data) => {
    window.consoleData = data;
    window.saved = [];
    document.querySelector("comfort-sense-panel").hass = {
      states: {},
      locale: { language: "en-US" },
      callWS: async (command) => {
        if (command.type === "comfort_sense/save") {
          window.saved.push(command);
          consoleData.entries[0].config = JSON.parse(JSON.stringify(command.config));
          consoleData.entries[0].revision = "saved";
          return { saved: true };
        }
        return JSON.parse(JSON.stringify(consoleData));
      },
    };
  }, data);
  await page.getByRole("heading", { name: "Upstairs", exact: true }).waitFor();
  assert.equal(await page.getByRole("heading", { name: "Heating unavailable", exact: true }).count(), 1);
  const nextAction = await page
    .getByRole("button", { name: "Check heater connection →", exact: true })
    .evaluate((el) => el.getBoundingClientRect().toJSON());
  assert.ok(nextAction.y + nextAction.height < (await page.evaluate(() => innerHeight)));
  assert.equal(await page.locator(".logo").evaluate((img) => img.complete && img.naturalWidth > 0), true);
  const output = process.env.SCREENSHOT_DIR;
  if (output) {
    fs.mkdirSync(output, { recursive: true });
    await page.screenshot({ path: path.join(output, "overview-desktop.png"), fullPage: true });
    for (const label of ["Rooms", "Schedules", "Heating", "Preferences"]) {
      await page.getByRole("tab", { name: label, exact: true }).click();
      await page.screenshot({
        path: path.join(output, label.toLowerCase() + "-desktop.png"),
        fullPage: true,
      });
    }
    await page.setViewportSize({ width: 390, height: 844 });
    for (const label of ["Overview", "Rooms", "Schedules", "Heating", "Preferences"]) {
      await page.getByRole("tab", { name: label, exact: true }).click();
      await page.screenshot({
        path: path.join(output, label.toLowerCase() + "-setup-mobile.png"),
        fullPage: true,
      });
    }
    await page.setViewportSize({ width: 1440, height: 1400 });
  }
  await page.getByRole("tab", { name: "Rooms", exact: true }).click();
  assert.equal(await page.getByRole("combobox", { name: "Temperature sensors" }).count(), 2);
  const order = await page.locator("comfort-sense-panel").evaluate((el) => {
    const root = el.shadowRoot;
    return {
      room: root.querySelector(".room-editor").getBoundingClientRect().top,
      behavior: [...root.querySelectorAll("summary")]
        .find((e) => e.textContent.includes("Room behavior"))
        .getBoundingClientRect().top,
    };
  });
  assert.ok(order.room < order.behavior);
  const picker = page.locator("sense-entity-picker").first();
  await picker.getByRole("combobox").fill("Study");
  await picker.getByRole("option").filter({ hasText: "Study temperature" }).click();
  assert.equal(
    await picker.getByRole("button", { name: "Remove Study temperature", exact: true }).count(),
    1,
  );
  await picker.getByRole("combobox").fill("power");
  assert.equal(await picker.getByRole("option").count(), 0);
  await picker.getByRole("combobox").press("Escape");
  await page.getByRole("button", { name: "Review & save" }).click();
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await page.getByRole("status").filter({ hasText: "Settings saved" }).waitFor();
  const saved = await page.evaluate(() => window.saved.at(-1));
  assert.equal(saved.unit, "°F");
  assert.equal(saved.config.comfort_temperature, 70);
  assert.equal(saved.config.rooms[0].id, "bedroom");
  assert.equal(saved.config.rooms[0].temperature_sensors.includes("sensor.new_room"), true);
  await page.getByRole("tab", { name: "Preferences", exact: true }).click();
  assert.equal(await page.getByText("Proportional · Kp", { exact: true }).count(), 0);
  await page.getByText("PID tuning & learning", { exact: true }).click();
  await page.getByRole("combobox", { name: "Average PID tuning", exact: true }).selectOption("manual");
  assert.equal(await page.getByText("Proportional · Kp", { exact: true }).count(), 1);
  await page.getByRole("button", { name: "Discard", exact: true }).click();
  await page.getByRole("tab", { name: "Schedules", exact: true }).click();
  await page.getByText("Edit morning alarms", { exact: true }).click();
  const alarm = page
    .locator("sense-entity-picker")
    .filter({ has: page.getByRole("combobox", { name: "Next-alarm sensors", exact: true }) });
  assert.equal(await alarm.getByText("2026-10-30T09:50:00Z", { exact: true }).count(), 0);
  await page.getByRole("button", { name: "+ Connect schedule" }).click();
  await page.getByRole("textbox", { name: "Schedule name", exact: true }).fill("Weekday wake-up");
  const schedule = page
    .locator("sense-entity-picker")
    .filter({ has: page.getByRole("combobox", { name: "Schedule helper" }) });
  await schedule.getByRole("combobox").fill("Weekday");
  await schedule.getByRole("option").filter({ hasText: "Weekday mornings" }).click();
  await page.getByRole("tab", { name: "Heating", exact: true }).click();
  await page.getByText("Protection & cycling", { exact: true }).click();
  await page.getByRole("spinbutton", { name: "Minimum on time (minutes)", exact: false }).fill("6");
  assert.equal(await page.locator("comfort-sense-panel").evaluate((el) => el.draft.min_on_seconds), 360);
  await page.getByRole("switch", { name: "Observation only (Shadow mode)" }).uncheck();
  await page.getByRole("button", { name: "Review & save" }).click();
  assert.equal(await page.getByRole("button", { name: "Save changes", exact: true }).isDisabled(), true);
  await page.getByRole("checkbox", { name: "I have stopped other controllers of this relay." }).check();
  assert.equal(await page.getByRole("button", { name: "Save changes", exact: true }).isEnabled(), true);
  await page.getByRole("button", { name: "Keep editing" }).click();
  await page.getByRole("button", { name: "Discard", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("tab", { name: "Rooms", exact: true }).click();
  const overflow = await page.locator("comfort-sense-panel").evaluate((el) => {
    let root = el.shadowRoot;
    return [...root.querySelectorAll("main,.card,.fields,header,.top,.footer")].some(
      (e) => e.scrollWidth > e.clientWidth + 2,
    );
  });
  assert.equal(overflow, false);
  if (output) await page.screenshot({ path: path.join(output, "rooms-mobile.png"), fullPage: true });
  await page.getByRole("tab", { name: "Overview", exact: true }).click();
  // HA's custom-panel ancestors need not declare a definite percentage height.
  // The save bar must still stay within the viewport on a long page.
  await page.evaluate(() => {
    const wrapper = document.createElement("div");
    document.body.append(wrapper);
    wrapper.append(document.querySelector("comfort-sense-panel"));
  });
  const layout = await page.locator("comfort-sense-panel").evaluate((el) => ({
    panel: el.getBoundingClientRect().height,
    footer: el.shadowRoot.querySelector(".footer").getBoundingClientRect().bottom,
    viewport: innerHeight,
  }));
  assert.ok(layout.footer <= layout.viewport + 1);
  assert.ok(Math.abs(layout.panel - layout.viewport) <= 1);
  if (output) await page.screenshot({ path: path.join(output, "overview-mobile.png"), fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.locator("comfort-sense-panel").evaluate((el) => {
    Object.entries({
      "--primary-background-color": "#111b21",
      "--card-background-color": "#19262e",
      "--primary-text-color": "#e6eef0",
      "--secondary-text-color": "#a4b8c1",
      "--divider-color": "#30434e",
      "--primary-color": "#61cccb",
      "--secondary-background-color": "#243640",
      "--text-primary-color": "#102226",
    }).forEach(([key, value]) => el.style.setProperty(key, value));
  });
  if (output) await page.screenshot({ path: path.join(output, "overview-dark.png"), fullPage: true });
  assert.deepEqual(errors, []);
  console.log(
    "Console browser checks passed: entity filters, preserved IDs, Fahrenheit payload, manual PID visibility, schedule draft, active-control review, mobile layout and logo.",
  );
  await browser.close();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
