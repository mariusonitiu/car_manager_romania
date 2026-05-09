class CarManagerRomaniaCard extends HTMLElement {
  setConfig(config) {
    this.config = config || {};
    this._editMode = this.config.edit_mode ?? false;
    this._selectedVehicle = this.config.vehicle || null;
    this._showDetails = this.config.show_details ?? false;
    this._expandedVehicles = this._expandedVehicles || new Set();
  }

  set hass(hass) {
    this._hass = hass;
    this.render();
  }

  getCardSize() {
    return 5;
  }

  render() {
    if (!this._hass) return;

    const vehicles = this._buildVehicles();
    const visibleVehicles = this._selectedVehicle
      ? vehicles.filter((vehicle) => this._matchesVehicle(vehicle, this._selectedVehicle))
      : vehicles;

    this.innerHTML = `
      <ha-card>
        <style>${this._styles()}</style>
        <div class="cmr-card">
          <div class="cmr-header">
            <div>
              <div class="cmr-title">${this._escape(this.config.title || "Car Manager România")}</div>
              <div class="cmr-subtitle">${visibleVehicles.length || 0} autovehicul${visibleVehicles.length === 1 ? "" : "e"} monitorizat${visibleVehicles.length === 1 ? "" : "e"}</div>
            </div>
            <button class="cmr-mode" data-action="toggle-mode">${this._editMode ? "Afișare" : "Editare"}</button>
          </div>
          ${visibleVehicles.length ? visibleVehicles.map((vehicle) => this._renderVehicle(vehicle)).join("") : this._renderEmpty()}
        </div>
      </ha-card>
    `;

    this._attachEvents();
  }

  _buildVehicles() {
    const registry = this._hass.entities || {};
    const devices = this._hass.devices || {};
    const groups = new Map();

    for (const [entityId, stateObj] of Object.entries(this._hass.states || {})) {
      const entityRegistry = registry[entityId] || {};
      if (entityRegistry.platform !== "car_manager_romania") continue;
      if (!this._isSupportedDomain(entityId)) continue;
      if (this._isTechnicalOrExternalRovinietaEntity(entityId, stateObj)) continue;

      const deviceId = entityRegistry.device_id || this._vehicleIdFromEntity(entityId) || this._guessVehicleKey(stateObj, entityId);
      const device = deviceId && devices[deviceId] ? devices[deviceId] : {};
      const key = deviceId || this._guessVehicleKey(stateObj, entityId) || "car_manager_romania";

      if (!groups.has(key)) {
        groups.set(key, {
          key,
          device,
          entities: [],
          label: device.name || null,
          plate: null,
          vin: null,
        });
      }

      const group = groups.get(key);
      group.entities.push({ entityId, stateObj, registry: entityRegistry });

      const attrs = stateObj.attributes || {};
      if (attrs.name) group.label = attrs.name;
      if (attrs.license_plate) group.plate = attrs.license_plate;
      if (attrs.vin) group.vin = attrs.vin;
      if (!group.label && attrs.friendly_name) group.label = this._cleanFriendlyName(attrs.friendly_name);
    }

    return [...groups.values()]
      .filter((group) => this._isConfiguredVehicleGroup(group))
      .map((group) => this._normalizeVehicle(group))
      .sort((a, b) => a.label.localeCompare(b.label, "ro"));
  }

  _normalizeVehicle(group) {
    const statusEntity = group.entities.find(({ entityId, stateObj }) =>
      entityId.startsWith("sensor.") && (stateObj.attributes || {}).license_plate
    );

    if (statusEntity) {
      const attrs = statusEntity.stateObj.attributes || {};
      group.label = attrs.name || group.label;
      group.plate = attrs.license_plate || group.plate;
      group.vin = attrs.vin || group.vin;
    }

    group.label = group.label || group.plate || "Autovehicul";
    group.entities.sort((a, b) => this._friendly(a).localeCompare(this._friendly(b), "ro"));
    return group;
  }

  _renderVehicle(vehicle) {
    const summary = this._extractSummary(vehicle);

    return `
      <section class="cmr-vehicle">
        <div class="cmr-vehicle-head">
          <div>
            <div class="cmr-vehicle-title">${this._escape(vehicle.label)}</div>
            <div class="cmr-plate">${this._escape(vehicle.plate || "Număr neconfigurat")}${vehicle.vin ? ` · VIN: ${this._escape(vehicle.vin)}` : ""}</div>
          </div>
          <div class="cmr-km">${this._escape(summary.km || "—")} km</div>
        </div>
        ${this._editMode ? this._renderEdit(vehicle) : this._renderDashboard(vehicle, summary)}
      </section>
    `;
  }

  _renderDashboard(vehicle, summary) {
    const expanded = this._showDetails || this._expandedVehicles.has(vehicle.key);
    return `
      <div class="cmr-grid">
        ${this._renderTile("Revizie", summary.serviceStatus, summary.serviceDays, summary.serviceKm, "mdi:wrench-clock")}
        ${this._renderTile("RCA", summary.rcaStatus, summary.rcaDays, summary.rcaExpiry, "mdi:shield-check")}
        ${this._renderTile("ITP", summary.itpStatus, summary.itpDays, summary.itpExpiry, "mdi:clipboard-check")}
        ${this._renderTile("Rovinietă", summary.rovinietaStatus, summary.rovinietaDays, summary.rovinietaExpiry, "mdi:road-variant")}
      </div>
      <div class="cmr-details-bar">
        <button class="cmr-details-button" data-action="toggle-details" data-vehicle="${this._escape(vehicle.key)}">
          ${expanded ? "Ascunde detalii" : "Detalii"}
        </button>
      </div>
      ${expanded ? `<div class="cmr-details">${this._renderMaintenance(vehicle)}${this._renderConsumables(vehicle)}${this._showDetails ? this._renderRovinietaDetails(vehicle) : ""}</div>` : ""}
    `;
  }

  _renderTile(title, status, main, sub, icon) {
    const stateClass = this._statusClass(status || main || sub);
    return `
      <div class="cmr-tile ${stateClass}">
        <div class="cmr-tile-top"><ha-icon icon="${icon}"></ha-icon><span class="cmr-tile-title">${this._escape(title)}</span></div>
        <div class="cmr-tile-main">${this._escape(this._formatMain(main))}</div>
        <div class="cmr-tile-sub">${this._escape(status || sub || "neconfigurat")}</div>
      </div>
    `;
  }

  _renderMaintenance(vehicle) {
    const groups = [
      { key: "revizie", title: "Revizie generală" },
      { key: "ulei cutie", title: "Ulei cutie viteze" },
      { key: "distribu", title: "Distribuție" },
      { key: "lichid fr", title: "Lichid frână" },
      { key: "antigel", title: "Lichid antigel" },
    ];

    const rows = groups.map((group) => {
      const status = this._findSensorByName(vehicle, [group.key, "status"]);
      const days = this._findMaintenanceRemainingDays(vehicle, group.key);
      const km = this._findMaintenanceRemainingKm(vehicle, group.key);
      if (!status && !days && !km) return "";
      return this._renderRow(
        group.title,
        this._entityValue(status),
        this._formatDays(this._entityValue(days)),
        this._formatKm(this._entityValue(km)),
        this._statusClass(this._entityValue(status)),
      );
    }).filter(Boolean).join("");

    if (!rows) return "";
    return `<div class="cmr-section"><div class="cmr-section-title">Mentenanță</div>${rows}</div>`;
  }

  _renderLegalDetails(summary) {
    const rows = [
      this._renderRow("RCA expiră la", summary.rcaExpiry, summary.rcaDays, summary.rcaStatus, this._statusClass(summary.rcaStatus || summary.rcaDays)),
      this._renderRow("ITP expiră la", summary.itpExpiry, summary.itpDays, summary.itpStatus, this._statusClass(summary.itpStatus || summary.itpDays)),
      this._renderRow("Rovinietă expiră la", summary.rovinietaExpiry, summary.rovinietaDays, summary.rovinietaStatus, this._statusClass(summary.rovinietaStatus || summary.rovinietaDays)),
    ].join("");

    return `<div class="cmr-section"><div class="cmr-section-title">Termene legale</div>${rows}</div>`;
  }

  _renderConsumables(vehicle) {
    const rows = vehicle.entities
      .filter(({ entityId, stateObj }) => entityId.startsWith("text.") && this._isConsumableName(this._friendly({ stateObj, entityId })))
      .map((entity) => this._renderRow(this._shortLabel(this._friendly(entity)), entity.stateObj.state || "—", "", "", ""))
      .join("");

    if (!rows) return "";
    return `<div class="cmr-section"><div class="cmr-section-title">Consumabile și specificații</div>${rows}</div>`;
  }

  _renderRovinietaDetails(vehicle) {
    const rows = vehicle.entities
      .filter(({ entityId, stateObj }) => entityId.startsWith("sensor.") && this._friendly({ stateObj, entityId }).toLowerCase().includes("roviniet"))
      .filter(({ stateObj }) => stateObj.state && stateObj.state !== "unknown" && stateObj.state !== "unavailable")
      .map((entity) => this._renderRow(this._shortLabel(this._friendly(entity)), entity.stateObj.state, "", "", this._statusClass(entity.stateObj.state)))
      .join("");

    if (!rows) return "";
    return `<div class="cmr-section"><div class="cmr-section-title">Detalii rovinietă</div>${rows}</div>`;
  }

  _renderEdit(vehicle) {
    const editable = this._uniqueEntities(
      vehicle.entities.filter(({ entityId }) => entityId.startsWith("number.") || entityId.startsWith("date.") || entityId.startsWith("text."))
    ).filter((entity) => this._isEditableField(entity));

    const groups = [
      { title: "Date autovehicul", test: (e) => this._isVehicleEditField(e) },
      { title: "Revizie generală", test: (e) => this._isMaintenanceEditField(e, ["revizie"]) },
      { title: "Ulei cutie viteze", test: (e) => this._isMaintenanceEditField(e, ["ulei cutie"]) },
      { title: "Distribuție", test: (e) => this._isMaintenanceEditField(e, ["distribu"]) },
      { title: "Lichid frână", test: (e) => this._isMaintenanceEditField(e, ["lichid fr"]) },
      { title: "Lichid antigel", test: (e) => this._isMaintenanceEditField(e, ["antigel"]) },
      { title: "RCA", test: (e) => this._isLegalEditField(e, "rca") },
      { title: "ITP", test: (e) => this._isLegalEditField(e, "itp") },
      { title: "Consumabile", test: (e) => this._isConsumableEditField(e) },
    ];

    const used = new Set();
    const content = groups.map((group) => {
      const fields = editable
        .filter((entity) => !used.has(entity.entityId) && group.test(entity))
        .sort((a, b) => this._editOrder(a).localeCompare(this._editOrder(b), "ro"));
      fields.forEach((entity) => used.add(entity.entityId));
      if (!fields.length) return "";
      return `<div class="cmr-edit-group"><div class="cmr-section-title">${group.title}</div>${fields.map((entity) => this._renderField(entity)).join("")}</div>`;
    }).filter(Boolean).join("");

    const buttons = vehicle.entities
      .filter(({ entityId }) => entityId.startsWith("button."))
      .map((entity) => `<button class="cmr-action" data-button="${entity.entityId}">${this._escape(this._friendly(entity))}</button>`)
      .join("");

    return `${content || this._renderEmpty()}${buttons ? `<div class="cmr-actions">${buttons}</div>` : ""}`;
  }

  _uniqueEntities(entities) {
    const seen = new Set();
    return entities.filter((entity) => {
      if (seen.has(entity.entityId)) return false;
      seen.add(entity.entityId);
      return true;
    });
  }

  _isEditableField(entity) {
    const name = this._normalize(this._friendly(entity));
    if (/zile ramase|km ramasi|status|valid|activ|expirat|ramase pana|ramasi pana/.test(name)) return false;
    return true;
  }

  _isVehicleEditField(entity) {
    return this._normalize(this._friendly(entity)).includes("kilometri actuali");
  }

  _isMaintenanceEditField(entity, terms) {
    const name = this._normalize(this._friendly(entity));
    const isTerm = terms.some((term) => name.includes(this._normalize(term)));
    const isMaintenanceInput = /ultimul schimb km|ultima data|interval km|interval zile/.test(name);
    return isTerm && isMaintenanceInput;
  }

  _isLegalEditField(entity, legalType) {
    const name = this._normalize(this._friendly(entity));
    if (!name.includes(legalType)) return false;
    if (legalType === "rca") {
      return /rca.*(incepe la|expira la|asigurator|numar polita|observatii)/.test(name);
    }
    if (legalType === "itp") {
      return /itp.*(incepe la|expira la|statie|numar raport|observatii)/.test(name);
    }
    return false;
  }

  _isConsumableEditField(entity) {
    const name = this._normalize(this._friendly(entity));
    if (/rca|itp|revizie|distribu|ultimul schimb|ultima data|interval/.test(name)) return false;
    return this._isConsumableName(this._friendly(entity));
  }

  _editOrder(entity) {
    const name = this._normalize(this._friendly(entity));
    const order = [
      "kilometri actuali",
      "ultima data", "ultimul schimb km", "interval km", "interval zile",
      "incepe la", "expira la", "asigurator", "numar polita", "statie", "numar raport", "observatii",
      "cantitate ulei", "ulei motor", "filtru ulei", "filtru aer", "filtru combustibil", "filtru habitaclu", "ulei cutie", "lichid frana", "lichid antigel", "kit distributie",
    ];
    const index = order.findIndex((item) => name.includes(item));
    return `${index === -1 ? 999 : index}`.padStart(3, "0") + name;
  }

  _renderField(entity) {
    const domain = entity.entityId.split(".")[0];
    const value = entity.stateObj.state === "unknown" || entity.stateObj.state === "unavailable" ? "" : entity.stateObj.state;
    const type = domain === "number" ? "number" : domain === "date" ? "date" : "text";
    return `
      <label class="cmr-field">
        <span>${this._escape(this._shortLabel(this._friendly(entity)))}</span>
        <input type="${type}" value="${this._escape(value)}" data-entity="${entity.entityId}" data-domain="${domain}">
      </label>
    `;
  }

  _renderRow(label, value, middle, right, cls) {
    return `
      <div class="cmr-row ${cls || ""}">
        <div class="cmr-row-label">${this._escape(label)}</div>
        <div class="cmr-row-value">${this._escape(value || "—")}</div>
        ${middle ? `<div class="cmr-row-muted">${this._escape(middle)}</div>` : ""}
        ${right ? `<div class="cmr-row-muted">${this._escape(right)}</div>` : ""}
      </div>
    `;
  }

  _renderEmpty() {
    return `<div class="cmr-empty">Nu am găsit autovehicule configurate în Car Manager România. Verifică dacă integrarea este încărcată și dacă există cel puțin un autovehicul cu număr de înmatriculare.</div>`;
  }

  _attachEvents() {
    this.querySelector('[data-action="toggle-mode"]')?.addEventListener("click", () => {
      this._editMode = !this._editMode;
      this.render();
    });

    this.querySelectorAll('button[data-action="toggle-details"]').forEach((button) => {
      button.addEventListener("click", () => {
        const key = button.dataset.vehicle;
        if (this._expandedVehicles.has(key)) {
          this._expandedVehicles.delete(key);
        } else {
          this._expandedVehicles.add(key);
        }
        this.render();
      });
    });

    this.querySelectorAll("input[data-entity]").forEach((input) => {
      input.addEventListener("change", (event) => this._saveField(event.currentTarget));
    });

    this.querySelectorAll("button[data-button]").forEach((button) => {
      button.addEventListener("click", () => {
        this._hass.callService("button", "press", {}, { entity_id: button.dataset.button });
      });
    });
  }

  _saveField(input) {
    const entityId = input.dataset.entity;
    const domain = input.dataset.domain;
    const value = input.value;

    if (domain === "number") {
      this._hass.callService("number", "set_value", { value: Number(value || 0) }, { entity_id: entityId });
    } else if (domain === "date") {
      this._hass.callService("date", "set_value", { date: value || null }, { entity_id: entityId });
    } else if (domain === "text") {
      this._hass.callService("text", "set_value", { value }, { entity_id: entityId });
    }
  }

  _extractSummary(vehicle) {
    const km = this._findSensorByName(vehicle, ["kilometri"]);
    const serviceStatus = this._findSensorByName(vehicle, ["revizie", "status"]);
    const serviceDays = this._findMaintenanceRemainingDays(vehicle, "revizie");
    const serviceKm = this._findMaintenanceRemainingKm(vehicle, "revizie");
    const rcaStatus = this._findSensorByName(vehicle, ["rca", "status"]);
    const rcaDays = this._findSensorByName(vehicle, ["rca", "zile", "ramase"]);
    const rcaExpiry = this._findByName(vehicle, ["rca", "expir"]);
    const itpStatus = this._findSensorByName(vehicle, ["itp", "status"]);
    const itpDays = this._findSensorByName(vehicle, ["itp", "zile", "ramase"]);
    const itpExpiry = this._findByName(vehicle, ["itp", "expir"]);
    const rovStatus = this._findSensorByName(vehicle, ["roviniet"], ["zile", "expir", "serie", "categorie", "perioad"]);
    const rovDays = this._findSensorByName(vehicle, ["roviniet", "zile", "ramase"]);
    const rovExpiry = this._findByName(vehicle, ["roviniet", "expir"]);

    return {
      km: this._entityValue(km),
      serviceStatus: this._entityValue(serviceStatus),
      serviceDays: this._formatDays(this._entityValue(serviceDays)),
      serviceKm: this._formatKm(this._entityValue(serviceKm)),
      rcaStatus: this._entityValue(rcaStatus),
      rcaDays: this._formatDays(this._entityValue(rcaDays)),
      rcaExpiry: this._entityValue(rcaExpiry),
      itpStatus: this._entityValue(itpStatus),
      itpDays: this._formatDays(this._entityValue(itpDays)),
      itpExpiry: this._entityValue(itpExpiry),
      rovinietaStatus: this._entityValue(rovStatus),
      rovinietaDays: this._formatDays(this._entityValue(rovDays)),
      rovinietaExpiry: this._entityValue(rovExpiry),
    };
  }


  _findSensorByName(vehicle, terms, excludeTerms = []) {
    const found = this._findByName(vehicle, terms, excludeTerms, (entity) => entity.entityId.startsWith("sensor."));
    if (found) return found;
    return this._findByName(vehicle, terms, excludeTerms);
  }

  _findMaintenanceRemainingDays(vehicle, key) {
    return this._findByName(
      vehicle,
      [key, "zile", "ramase"],
      ["interval", "ultim", "ultima"],
      (entity) => entity.entityId.startsWith("sensor."),
    );
  }

  _findMaintenanceRemainingKm(vehicle, key) {
    return this._findByName(
      vehicle,
      [key, "km", "ramasi"],
      ["interval", "ultim", "ultima", "actuali"],
      (entity) => entity.entityId.startsWith("sensor."),
    );
  }

  _entityValue(entity) {
    if (!entity) return null;
    const value = entity.stateObj?.state;
    if (value === undefined || value === null || value === "" || value === "unknown" || value === "unavailable") return null;
    return value;
  }

  _formatDays(value) {
    if (value === undefined || value === null || value === "") return "—";
    return `${value} zile`;
  }

  _formatKm(value) {
    if (value === undefined || value === null || value === "") return "—";
    return `${value} km`;
  }

  _findByName(vehicle, terms, excludeTerms = [], predicate = null) {
    const normalizedTerms = terms.map((term) => this._normalize(term));
    const normalizedExcludes = excludeTerms.map((term) => this._normalize(term));
    return vehicle.entities.find((entity) => {
      if (predicate && !predicate(entity)) return false;
      const name = this._normalize(this._friendly(entity));
      return normalizedTerms.every((term) => name.includes(term)) && !normalizedExcludes.some((term) => name.includes(term));
    });
  }

  _friendly(entity) {
    return (entity.stateObj?.attributes?.friendly_name || entity.entityId || "").toString();
  }

  _shortLabel(label) {
    return label
      .replace(/^Car Manager România\s*/i, "")
      .replace(/^Autovehicul\s*/i, "")
      .trim();
  }

  _cleanFriendlyName(label) {
    return label.replace(/\s+(Kilometri|Status|RCA|ITP|Rovinietă|Revizie|Ulei|Distribuție|Lichid).*$/i, "").trim();
  }

  _isConsumableName(label) {
    return /ulei motor|cantitate ulei|filtru|ulei cutie|lichid frână|lichid antigel|kit distribuție/i.test(label);
  }

  _isSupportedDomain(entityId) {
    return /^(sensor|number|date|text|button)\./.test(entityId);
  }

  _isConfiguredVehicleGroup(group) {
    const label = this._normalize(group.label || "");
    if (!group.entities.length) return false;
    if (label.includes("e-rovinieta") || label === "rovinieta" || label.includes("rovinieta.ro")) return false;
    if (label.includes("car manager romania") && !group.plate) return false;

    const hasPlate = Boolean(group.plate);
    const hasCoreVehicleEntity = group.entities.some((entity) => {
      const name = this._normalize(this._friendly(entity));
      return name.includes("kilometri") || name.endsWith(" status") || name.includes("revizie") || name.includes("rca") || name.includes("itp");
    });
    const onlyRovinieta = group.entities.every((entity) => this._normalize(this._friendly(entity)).includes("roviniet"));

    return hasPlate || (hasCoreVehicleEntity && !onlyRovinieta);
  }

  _isTechnicalOrExternalRovinietaEntity(entityId, stateObj) {
    const name = this._normalize((stateObj.attributes || {}).friendly_name || entityId);
    if (name.includes("e-rovinieta.ro") || name.includes("erovinieta")) return true;
    if (name.includes("vehicle ") && name.includes("roviniet")) return true;
    if (name.includes("utilizator") || name.includes("account") || name.includes("cont")) return true;
    return false;
  }

  _vehicleIdFromEntity(entityId) {
    const objectId = entityId.split(".")[1] || "";
    const knownSuffixes = [
      "_kilometri", "_km", "_status", "_rca_status", "_itp_status", "_rovinieta_status",
      "_rca_expiry", "_itp_expiry", "_rovinieta_expiry", "_revizie_generala_status",
    ];
    for (const suffix of knownSuffixes) {
      if (objectId.endsWith(suffix)) return objectId.slice(0, -suffix.length);
    }
    return null;
  }

  _guessVehicleKey(stateObj, entityId) {
    const attrs = stateObj.attributes || {};
    return attrs.license_plate || attrs.vin || this._cleanFriendlyName(attrs.friendly_name || entityId) || entityId;
  }

  _matchesVehicle(vehicle, wanted) {
    const needle = this._normalize(wanted);
    return this._normalize(vehicle.label).includes(needle) || this._normalize(vehicle.plate || "").includes(needle);
  }

  _formatMain(value) {
    if (value === undefined || value === null || value === "") return "—";
    return value;
  }

  _statusClass(value) {
    const text = this._normalize(value || "");
    if (/expirat|depasit|fara|overdue|invalid/.test(text)) return "is-bad";
    if (/curand|soon|astazi|0 zile|1 zile|2 zile|3 zile|4 zile|5 zile|6 zile|7 zile|8 zile|9 zile|10 zile|11 zile|12 zile|13 zile|14 zile|15 zile|16 zile|17 zile|18 zile|19 zile|20 zile|21 zile|22 zile|23 zile|24 zile|25 zile|26 zile|27 zile|28 zile|29 zile|30 zile/.test(text)) return "is-warn";
    if (/ok|valid|activ|configurat|finalizat/.test(text)) return "is-good";
    return "is-neutral";
  }

  _normalize(value) {
    return (value || "")
      .toString()
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "");
  }

  _escape(value) {
    return (value ?? "").toString().replace(/[&<>'"]/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "'": "&#39;",
      '"': "&quot;",
    }[char]));
  }

  _styles() {
    return `
      .cmr-card { padding: 16px; }
      .cmr-header, .cmr-vehicle-head { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
      .cmr-title { font-size: 20px; font-weight: 800; letter-spacing: -0.02em; }
      .cmr-subtitle, .cmr-plate, .cmr-row-muted, .cmr-tile-sub { color: var(--secondary-text-color); font-size: 12px; }
      .cmr-mode, .cmr-action { border: 0; border-radius: 999px; padding: 8px 12px; color: var(--primary-text-color); background: color-mix(in srgb, var(--primary-color) 14%, transparent); cursor: pointer; font-weight: 700; }
      .cmr-vehicle { margin-top: 16px; padding: 14px; border-radius: 18px; background: color-mix(in srgb, var(--card-background-color) 86%, var(--primary-color) 14%); border: 1px solid var(--divider-color); }
      .cmr-vehicle-title { font-size: 17px; font-weight: 800; }
      .cmr-km { white-space: nowrap; font-weight: 800; font-size: 18px; }
      .cmr-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin-top: 14px; }
      .cmr-tile { padding: 9px 7px; border-radius: 16px; background: var(--card-background-color); border: 1px solid var(--divider-color); min-height: 88px; overflow: hidden; }
      .cmr-tile-top { display: flex; flex-direction: column; align-items: flex-start; gap: 3px; font-size: 10.5px; line-height: 1.1; font-weight: 900; color: var(--secondary-text-color); }
      .cmr-tile-title { max-width: 100%; white-space: normal; overflow-wrap: anywhere; }
      .cmr-tile-top ha-icon { width: 18px; height: 18px; flex: 0 0 auto; }
      .cmr-tile-main { margin-top: 8px; font-size: 17px; font-weight: 900; }
      .cmr-details-bar { display: flex; justify-content: center; margin-top: 12px; }
      .cmr-details-button { border: 0; border-radius: 999px; padding: 8px 16px; background: color-mix(in srgb, var(--primary-color) 16%, transparent); color: var(--primary-text-color); font-weight: 800; cursor: pointer; }
      .cmr-details { margin-top: 4px; }
      .cmr-section, .cmr-edit-group { margin-top: 14px; padding: 12px; border-radius: 16px; background: color-mix(in srgb, var(--card-background-color) 92%, var(--primary-color) 8%); }
      .cmr-section-title { font-size: 13px; font-weight: 900; margin-bottom: 8px; color: var(--primary-text-color); }
      .cmr-row { display: grid; grid-template-columns: 1.35fr .9fr auto auto; gap: 8px; align-items: center; padding: 8px 0; border-top: 1px solid color-mix(in srgb, var(--divider-color) 70%, transparent); }
      .cmr-row:first-of-type { border-top: 0; }
      .cmr-row-label { font-weight: 700; }
      .cmr-row-value { font-weight: 800; }
      .is-good { --cmr-accent: #2e9d58; }
      .is-warn { --cmr-accent: #d99a22; }
      .is-bad { --cmr-accent: #d64545; }
      .is-neutral { --cmr-accent: var(--secondary-text-color); }
      .cmr-tile.is-good, .cmr-tile.is-warn, .cmr-tile.is-bad { border-left: 5px solid var(--cmr-accent); }
      .cmr-row.is-good .cmr-row-value, .cmr-row.is-warn .cmr-row-value, .cmr-row.is-bad .cmr-row-value { color: var(--cmr-accent); }
      .cmr-field { display: grid; grid-template-columns: 1fr minmax(120px, 260px); align-items: center; gap: 10px; padding: 7px 0; border-top: 1px solid color-mix(in srgb, var(--divider-color) 70%, transparent); font-weight: 700; }
      .cmr-field:first-of-type { border-top: 0; }
      .cmr-field input { width: 100%; box-sizing: border-box; border: 1px solid var(--divider-color); border-radius: 10px; padding: 8px 10px; background: var(--card-background-color); color: var(--primary-text-color); }
      .cmr-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
      .cmr-empty { margin-top: 14px; color: var(--secondary-text-color); padding: 14px; border: 1px dashed var(--divider-color); border-radius: 14px; }
      @media (max-width: 760px) {
        .cmr-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 6px; }
        .cmr-tile { padding: 8px 5px; min-height: 84px; }
        .cmr-tile-main { font-size: 16px; }
        .cmr-tile-sub { font-size: 11px; }
        .cmr-tile-top { font-size: 9.5px; }
        .cmr-row { grid-template-columns: 1fr; }
        .cmr-field { grid-template-columns: 1fr; }
      }
    `;
  }
}

customElements.define("car-manager-romania-card", CarManagerRomaniaCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "car-manager-romania-card",
  name: "Car Manager România Card",
  description: "Card pentru afișarea și administrarea datelor autovehiculelor din integrarea Car Manager România.",
});
