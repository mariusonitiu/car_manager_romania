class CarManagerRomaniaCard extends HTMLElement {
  setConfig(config) {
    this.config = config || {};
    this._editMode = this.config.edit_mode ?? false;
    this._selectedVehicle = this.config.vehicle || null;
    this._showDetails = this.config.show_details ?? false;
    this._expandedVehicles = this._expandedVehicles || new Set();
    this._addVehicleOpen = this._addVehicleOpen || false;
    this._addVehicleBusy = this._addVehicleBusy || false;
    this._addVehicleMessage = this._addVehicleMessage || "";
    this._vehicleActionBusy = this._vehicleActionBusy || null;
    this._vehicleActionMessage = this._vehicleActionMessage || "";
    this._localInactiveVehicles = this._localInactiveVehicles || new Map();
    this._inactiveVehicleIds = this._inactiveVehicleIds || new Set();
    this._addVehicleDraft = this._addVehicleDraft || {
      name: "",
      license_plate: "",
      vin: "",
      km: "0",
    };
    this._inputEditing = this._inputEditing || false;
  }

  set hass(hass) {
    this._hass = hass;

    // Home Assistant actualizează cardul des. Dacă utilizatorul scrie într-un input,
    // nu randăm din nou cardul, altfel textul introdus se pierde.
    if (this._inputEditing || this._isInputFocused()) {
      this._renderPending = true;
      return;
    }

    this.render();
  }

  getCardSize() {
    return 5;
  }

  render() {
    if (!this._hass) return;

    const inactiveVehiclesAll = this._buildInactiveVehicles();
    this._inactiveVehicleIds = new Set(inactiveVehiclesAll.map((vehicle) => vehicle.vehicle_id).filter(Boolean));

    const vehicles = this._buildVehicles();
    const visibleVehicles = this._selectedVehicle
      ? vehicles.filter((vehicle) => this._matchesVehicle(vehicle, this._selectedVehicle))
      : vehicles;
    const inactiveVehicles = inactiveVehiclesAll.filter((vehicle) =>
      this._selectedVehicle ? this._matchesVehicle(vehicle, this._selectedVehicle) : true
    );

    this.innerHTML = `
      <ha-card>
        <style>${this._styles()}</style>
        <div class="cmr-card">
          <div class="cmr-header">
            <div>
              <div class="cmr-title">${this._escape(this.config.title || "Car Manager România")}</div>
              <div class="cmr-subtitle">${visibleVehicles.length || 0} autovehicul${visibleVehicles.length === 1 ? "" : "e"} monitorizat${visibleVehicles.length === 1 ? "" : "e"}</div>
            </div>
            <div class="cmr-header-actions">
              <button class="cmr-mode" data-action="toggle-add-vehicle">Adaugă autovehicul</button>
              <button class="cmr-mode" data-action="toggle-mode">${this._editMode ? "Afișare" : "Editare"}</button>
            </div>
          </div>
          ${this._addVehicleOpen ? this._renderAddVehicleForm() : ""}
          ${this._editMode && inactiveVehicles.length ? this._renderInactiveVehicles(inactiveVehicles) : ""}
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
      const vehicleId = this._vehicleIdFromDevice(device) || this._vehicleIdFromEntityRegistry(entityRegistry, entityId);

      if (!groups.has(key)) {
        groups.set(key, {
          key,
          device,
          vehicle_id: vehicleId,
          entities: [],
          label: device.name || null,
          plate: null,
          vin: null,
        });
      }

      const group = groups.get(key);
      group.entities.push({ entityId, stateObj, registry: entityRegistry });
      if (stateObj.state && stateObj.state !== "unknown" && stateObj.state !== "unavailable") {
        group.hasAvailableEntity = true;
      }

      const attrs = stateObj.attributes || {};
      if (attrs.vehicle_id) group.vehicle_id = attrs.vehicle_id;
      if (attrs.name) group.label = attrs.name;
      if (attrs.license_plate) group.plate = attrs.license_plate;
      if (attrs.vin) group.vin = attrs.vin;
      if (!group.label && attrs.friendly_name) group.label = this._cleanFriendlyName(attrs.friendly_name);
    }

    return [...groups.values()]
      .filter((group) => !this._isInactiveVehicleGroup(group))
      .filter((group) => this._isConfiguredVehicleGroup(group))
      .map((group) => this._normalizeVehicle(group))
      .filter((vehicle) => !this._inactiveVehicleIds.has(vehicle.vehicle_id))
      .sort((a, b) => a.label.localeCompare(b.label, "ro"));
  }

  _buildInactiveVehicles() {
    const vehiclesById = new Map();

    for (const vehicle of this._localInactiveVehicles?.values?.() || []) {
      if (!vehicle?.vehicle_id) continue;
      vehiclesById.set(vehicle.vehicle_id, {
        key: vehicle.vehicle_id,
        vehicle_id: vehicle.vehicle_id,
        label: vehicle.label || vehicle.name || vehicle.license_plate || "Autovehicul dezactivat",
        plate: vehicle.plate || vehicle.license_plate || "",
        vin: vehicle.vin || "",
        km: vehicle.km ?? 0,
      });
    }

    for (const stateObj of Object.values(this._hass.states || {})) {
      const attrs = stateObj.attributes || {};
      const inactive = attrs.inactive_vehicles;
      if (!Array.isArray(inactive)) continue;

      for (const vehicle of inactive) {
        if (!vehicle || typeof vehicle !== "object") continue;

        const vehicleId = (vehicle.vehicle_id || "").toString();
        if (!vehicleId || vehiclesById.has(vehicleId)) continue;

        vehiclesById.set(vehicleId, {
          key: vehicleId,
          vehicle_id: vehicleId,
          label: vehicle.name || vehicle.license_plate || "Autovehicul dezactivat",
          plate: vehicle.license_plate || "",
          vin: vehicle.vin || "",
          km: vehicle.km ?? 0,
        });
      }
    }

    return [...vehiclesById.values()].sort((a, b) => a.label.localeCompare(b.label, "ro"));
  }

  _normalizeVehicle(group) {
    const statusEntity = group.entities.find(({ entityId, stateObj }) =>
      entityId.startsWith("sensor.") && (stateObj.attributes || {}).license_plate
    );

    if (statusEntity) {
      const attrs = statusEntity.stateObj.attributes || {};
      group.vehicle_id = attrs.vehicle_id || group.vehicle_id;
      group.label = attrs.name || group.label;
      group.plate = attrs.license_plate || group.plate;
      group.vin = attrs.vin || group.vin;
    }

    group.vehicle_id = group.vehicle_id || this._vehicleIdFromEntityRegistry(group.entities[0]?.registry || {}, group.entities[0]?.entityId || "") || group.key;
    group.label = group.label || group.plate || "Autovehicul";
    group.entities.sort((a, b) => this._friendly(a).localeCompare(this._friendly(b), "ro"));
    return group;
  }

  _renderAddVehicleForm() {
    const draft = this._addVehicleDraft || {};
    return `
      <form class="cmr-add-form" data-form="add-vehicle">
        <div class="cmr-section-title">Adăugare autovehicul</div>
        <div class="cmr-add-grid">
          <label class="cmr-field cmr-add-field">
            <span>Nume</span>
            <input type="text" name="name" required placeholder="Opel Insignia A" value="${this._escape(draft.name || "")}">
          </label>
          <label class="cmr-field cmr-add-field">
            <span>Nr. înmatriculare</span>
            <input type="text" name="license_plate" placeholder="SB01ABC" value="${this._escape(draft.license_plate || "")}">
          </label>
          <label class="cmr-field cmr-add-field">
            <span>VIN</span>
            <input type="text" name="vin" placeholder="opțional" value="${this._escape(draft.vin || "")}">
          </label>
          <label class="cmr-field cmr-add-field">
            <span>Km actuali</span>
            <input type="number" name="km" min="0" step="1" value="${this._escape(draft.km ?? "0")}">
          </label>
        </div>
        <div class="cmr-add-actions">
          <button class="cmr-action" type="submit" ${this._addVehicleBusy ? "disabled" : ""}>${this._addVehicleBusy ? "Se adaugă..." : "Salvează autovehicul"}</button>
          <button class="cmr-action cmr-secondary" type="button" data-action="cancel-add-vehicle">Anulează</button>
        </div>
        ${this._addVehicleMessage ? `<div class="cmr-message">${this._escape(this._addVehicleMessage)}</div>` : ""}
      </form>
    `;
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
      .map((entity) => this._renderSpecRow(this._specLabel(this._friendly(entity)), entity.stateObj.state || "—"))
      .join("");

    if (!rows) return "";
    return `<div class="cmr-section cmr-spec-section"><div class="cmr-section-title">Consumabile și specificații</div>${rows}</div>`;
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

    const admin = this._renderVehicleAdmin(vehicle);

    return `${content || this._renderEmpty()}${buttons ? `<div class="cmr-actions">${buttons}</div>` : ""}${admin}`;
  }

  _renderInactiveVehicles(vehicles) {
    const rows = vehicles.map((vehicle) => {
      const busy = this._vehicleActionBusy === vehicle.vehicle_id;
      const meta = [vehicle.plate, vehicle.vin ? `VIN: ${vehicle.vin}` : "", vehicle.km ? `${vehicle.km} km` : ""]
        .filter(Boolean)
        .join(" · ");

      return `
        <div class="cmr-inactive-row">
          <div>
            <div class="cmr-inactive-title">${this._escape(vehicle.label)}</div>
            <div class="cmr-plate">${this._escape(meta || "Fără detalii")}</div>
          </div>
          <button class="cmr-action" data-action="restore-vehicle" data-vehicle-id="${this._escape(vehicle.vehicle_id)}" data-vehicle-name="${this._escape(vehicle.label)}" ${busy ? "disabled" : ""}>
            ${busy ? "Se reactivează..." : "Reactivează"}
          </button>
        </div>
      `;
    }).join("");

    const message = this._vehicleActionMessage && this._vehicleActionBusy === null ? `<div class="cmr-message">${this._escape(this._vehicleActionMessage)}</div>` : "";

    return `
      <div class="cmr-edit-group cmr-inactive-zone">
        <div class="cmr-section-title">Autovehicule dezactivate</div>
        <div class="cmr-help">Aceste autovehicule sunt păstrate în storage, dar nu mai au entități active până la reactivare.</div>
        ${rows}
        ${message}
      </div>
    `;
  }

  _renderVehicleAdmin(vehicle) {
    const vehicleId = vehicle.vehicle_id || "";
    const busy = this._vehicleActionBusy === vehicleId;
    const message = this._vehicleActionMessage && this._vehicleActionBusy === null ? `<div class="cmr-message">${this._escape(this._vehicleActionMessage)}</div>` : "";

    if (!vehicleId) {
      return `
        <div class="cmr-edit-group cmr-danger-zone">
          <div class="cmr-section-title">Administrare autovehicul</div>
          <div class="cmr-help">Nu am putut identifica ID-ul intern al autovehiculului. Reîncarcă integrarea după actualizare și încearcă din nou.</div>
        </div>
      `;
    }

    return `
      <div class="cmr-edit-group cmr-danger-zone">
        <div class="cmr-section-title">Administrare autovehicul</div>
        <div class="cmr-help">Dezactivarea ascunde autovehiculul din lista principală și îl mută la Autovehicule dezactivate. Datele rămân păstrate în storage și poate fi reactivat oricând.</div>
        <div class="cmr-actions">
          <button class="cmr-action cmr-danger" data-action="remove-vehicle" data-vehicle-id="${this._escape(vehicleId)}" data-vehicle-name="${this._escape(vehicle.label)}" data-vehicle-plate="${this._escape(vehicle.plate || "")}" data-vehicle-vin="${this._escape(vehicle.vin || "")}" data-vehicle-km="${this._escape(this._extractSummary(vehicle).km || "")}" ${busy ? "disabled" : ""}>
            ${busy ? "Se dezactivează..." : "Dezactivează autovehicul"}
          </button>
        </div>
        ${message}
      </div>
    `;
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
        <span>${this._escape(this._fieldLabel(this._friendly(entity)))}</span>
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

  _renderSpecRow(label, value) {
    return `
      <div class="cmr-spec-row">
        <div class="cmr-spec-label">${this._escape(label)}</div>
        <div class="cmr-spec-value">${this._escape(value || "—")}</div>
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

    this.querySelector('[data-action="toggle-add-vehicle"]')?.addEventListener("click", () => {
      this._addVehicleOpen = !this._addVehicleOpen;
      this._addVehicleMessage = "";
      this.render();
    });

    this.querySelector('[data-action="cancel-add-vehicle"]')?.addEventListener("click", () => {
      this._addVehicleOpen = false;
      this._addVehicleMessage = "";
      this.render();
    });

    const addVehicleForm = this.querySelector('form[data-form="add-vehicle"]');
    addVehicleForm?.addEventListener("submit", (event) => {
      event.preventDefault();
      this._captureAddVehicleDraft(event.currentTarget);
      this._inputEditing = false;
      this._addVehicle(event.currentTarget);
    });
    addVehicleForm?.addEventListener("input", () => {
      this._captureAddVehicleDraft(addVehicleForm);
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

    this.querySelectorAll('button[data-action="remove-vehicle"]').forEach((button) => {
      button.addEventListener("click", () => {
        this._removeVehicle(button.dataset.vehicleId, button.dataset.vehicleName || "autovehiculul selectat", {
          label: button.dataset.vehicleName || "Autovehicul dezactivat",
          plate: button.dataset.vehiclePlate || "",
          vin: button.dataset.vehicleVin || "",
          km: button.dataset.vehicleKm || "",
        });
      });
    });

    this.querySelectorAll('button[data-action="restore-vehicle"]').forEach((button) => {
      button.addEventListener("click", () => {
        this._restoreVehicle(button.dataset.vehicleId, button.dataset.vehicleName || "autovehiculul selectat");
      });
    });

    this.querySelectorAll("input").forEach((input) => {
      input.addEventListener("focusin", () => {
        this._inputEditing = true;
      });
      input.addEventListener("focusout", () => {
        window.setTimeout(() => {
          this._inputEditing = this._isInputFocused();
          if (this._renderPending && !this._inputEditing) {
            this._renderPending = false;
            this.render();
          }
        }, 150);
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

  _isInputFocused() {
    let active = this.getRootNode?.()?.activeElement || this.ownerDocument?.activeElement;

    // În Home Assistant cardul poate fi randat în mai multe shadow root-uri.
    // Coborâm până la elementul activ real, altfel document.activeElement poate fi doar host-ul.
    while (active?.shadowRoot?.activeElement) {
      active = active.shadowRoot.activeElement;
    }

    if (!active || !this.contains(active)) return false;
    return active.matches?.("input, textarea, select, mwc-textfield, ha-textfield") || false;
  }

  _captureAddVehicleDraft(form) {
    if (!form) return;
    const data = new FormData(form);
    this._addVehicleDraft = {
      name: (data.get("name") || "").toString(),
      license_plate: (data.get("license_plate") || "").toString(),
      vin: (data.get("vin") || "").toString(),
      km: (data.get("km") || "0").toString(),
    };
  }

  async _addVehicle(form) {
    if (!this._hass || this._addVehicleBusy) return;

    const data = new FormData(form);
    const name = (data.get("name") || "").toString().trim();
    const licensePlate = (data.get("license_plate") || "").toString().trim().toUpperCase();
    const vin = (data.get("vin") || "").toString().trim().toUpperCase();
    const km = Number(data.get("km") || 0);

    if (!name) {
      this._addVehicleMessage = "Completează numele autovehiculului.";
      this.render();
      return;
    }

    this._addVehicleBusy = true;
    this._addVehicleMessage = "";
    this.render();

    try {
      await this._hass.callService("car_manager_romania", "add_vehicle", {
        name,
        license_plate: licensePlate,
        vin,
        km: Number.isFinite(km) && km > 0 ? Math.round(km) : 0,
      });
      this._addVehicleMessage = "Autovehiculul a fost adăugat. Entitățile se vor încărca după reîncărcarea integrării.";
      this._addVehicleDraft = { name: "", license_plate: "", vin: "", km: "0" };
      this._addVehicleOpen = false;
    } catch (error) {
      this._addVehicleMessage = error?.message || "Nu am putut adăuga autovehiculul.";
    } finally {
      this._addVehicleBusy = false;
      this.render();
    }
  }

  async _removeVehicle(vehicleId, vehicleName, vehicleMeta = {}) {
    if (!this._hass || !vehicleId || this._vehicleActionBusy) return;

    const confirmed = window.confirm(
      `Sigur vrei să dezactivezi ${vehicleName}?\n\nAutovehiculul va fi ascuns din card după reîncărcarea integrării, iar datele lui vor rămâne păstrate în storage.`
    );
    if (!confirmed) return;

    this._vehicleActionBusy = vehicleId;
    this._vehicleActionMessage = "";
    this.render();

    try {
      await this._hass.callService("car_manager_romania", "remove_vehicle", {
        vehicle_id: vehicleId,
      });
      this._localInactiveVehicles.set(vehicleId, {
        vehicle_id: vehicleId,
        label: vehicleMeta.label || vehicleName || "Autovehicul dezactivat",
        plate: vehicleMeta.plate || "",
        vin: vehicleMeta.vin || "",
        km: vehicleMeta.km || "",
      });
      this._inactiveVehicleIds.add(vehicleId);
      this._vehicleActionMessage = "Autovehiculul a fost dezactivat. Îl găsești la Autovehicule dezactivate, de unde îl poți reactiva.";
    } catch (error) {
      this._vehicleActionMessage = error?.message || "Nu am putut dezactiva autovehiculul.";
    } finally {
      this._vehicleActionBusy = null;
      this.render();
    }
  }

  async _restoreVehicle(vehicleId, vehicleName) {
    if (!this._hass || !vehicleId || this._vehicleActionBusy) return;

    const confirmed = window.confirm(
      `Reactivezi ${vehicleName}?\n\nAutovehiculul va fi încărcat din nou, iar entitățile vor reapărea după reîncărcarea integrării.`
    );
    if (!confirmed) return;

    this._vehicleActionBusy = vehicleId;
    this._vehicleActionMessage = "";
    this.render();

    try {
      await this._hass.callService("car_manager_romania", "restore_vehicle", {
        vehicle_id: vehicleId,
      });
      this._localInactiveVehicles.delete(vehicleId);
      this._inactiveVehicleIds.delete(vehicleId);
      this._vehicleActionMessage = "Autovehiculul a fost reactivat. Integrarea se reîncarcă.";
    } catch (error) {
      this._vehicleActionMessage = error?.message || "Nu am putut reactiva autovehiculul.";
    } finally {
      this._vehicleActionBusy = null;
      this.render();
    }
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

  _fieldLabel(label) {
    const cleaned = this._shortLabel(label);
    const parts = cleaned.split(/\s+-\s+/);
    if (parts.length > 1) return this._sentenceCase(parts.slice(1).join(" - "));
    return this._specLabel(cleaned);
  }

  _specLabel(label) {
    const cleaned = this._shortLabel(label);
    const patterns = [
      /cantitate ulei motor/i,
      /filtru combustibil/i,
      /filtru habitaclu/i,
      /filtru ulei/i,
      /filtru aer/i,
      /ulei cutie viteze/i,
      /ulei motor/i,
      /lichid frână/i,
      /lichid frana/i,
      /lichid antigel/i,
      /kit distribuție/i,
      /kit distributie/i,
      /kilometri actuali/i,
      /număr poliță/i,
      /numar polita/i,
      /număr raport/i,
      /numar raport/i,
      /asigurător/i,
      /asigurator/i,
      /observații/i,
      /observatii/i,
      /începe la/i,
      /incepe la/i,
      /expiră la/i,
      /expira la/i,
      /stație/i,
      /statie/i,
      /ultima dată/i,
      /ultima data/i,
      /ultimul schimb km/i,
      /interval km/i,
      /interval zile/i,
    ];

    for (const pattern of patterns) {
      const match = cleaned.match(pattern);
      if (match?.index !== undefined) return this._sentenceCase(cleaned.slice(match.index));
    }

    return cleaned;
  }

  _sentenceCase(value) {
    const text = (value || "").trim();
    if (!text) return text;
    return text.charAt(0).toUpperCase() + text.slice(1);
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

  _isInactiveVehicleGroup(group) {
    const inactiveIds = this._inactiveVehicleIds || new Set();
    if (!inactiveIds.size) return false;

    const candidates = new Set();
    if (group.vehicle_id) candidates.add(group.vehicle_id.toString());
    if (group.key) candidates.add(group.key.toString());
    const deviceVehicleId = this._vehicleIdFromDevice(group.device || {});
    if (deviceVehicleId) candidates.add(deviceVehicleId.toString());

    for (const entity of group.entities || []) {
      const attrs = entity.stateObj?.attributes || {};
      if (attrs.vehicle_id) candidates.add(attrs.vehicle_id.toString());
      const registryVehicleId = this._vehicleIdFromEntityRegistry(entity.registry || {}, entity.entityId || "");
      if (registryVehicleId) candidates.add(registryVehicleId.toString());
      const entityVehicleId = this._vehicleIdFromEntity(entity.entityId || "");
      if (entityVehicleId) candidates.add(entityVehicleId.toString());
    }

    for (const candidate of candidates) {
      if (inactiveIds.has(candidate)) return true;
    }
    return false;
  }

  _isConfiguredVehicleGroup(group) {
    const label = this._normalize(group.label || "");
    if (!group.entities.length) return false;
    // După dezactivarea unui autovehicul, Home Assistant păstrează în registry
    // entitățile vechi ca unavailable. Nu le mai tratăm ca autovehicule active,
    // altfel cardul afișează o mașină goală și ascunde fluxul de reactivare.
    if (!group.hasAvailableEntity) return false;
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

  _vehicleIdFromDevice(device) {
    const identifiers = device?.identifiers || [];
    for (const identifier of identifiers) {
      if (Array.isArray(identifier) && identifier[0] === "car_manager_romania" && identifier[1]) {
        return identifier[1].toString();
      }
      if (typeof identifier === "string" && identifier.includes("car_manager_romania")) {
        const parts = identifier.split(/[,:|]/).map((part) => part.trim()).filter(Boolean);
        const index = parts.indexOf("car_manager_romania");
        if (index !== -1 && parts[index + 1]) return parts[index + 1];
      }
    }
    return null;
  }

  _vehicleIdFromEntityRegistry(entityRegistry, entityId) {
    const uniqueId = entityRegistry?.unique_id || "";
    const objectId = (entityId || "").split(".")[1] || "";
    const suffixes = [
      "_km", "_kilometri", "_status", "_service_status", "_service_days_remaining", "_service_km_remaining",
      "_rca_status", "_rca_days_remaining", "_itp_status", "_itp_days_remaining",
      "_maintenance_gearbox_oil_status", "_maintenance_timing_belt_status", "_maintenance_brake_fluid_status", "_maintenance_coolant_status",
    ];

    for (const suffix of suffixes) {
      if (uniqueId.endsWith(suffix)) {
        const candidate = uniqueId.slice(0, -suffix.length);
        const parts = candidate.split("_");
        return parts.length > 1 ? parts.slice(1).join("_") || candidate : candidate;
      }
    }

    for (const suffix of suffixes) {
      if (objectId.endsWith(suffix)) return objectId.slice(0, -suffix.length);
    }

    return null;
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
      .cmr-card { padding: 16px; container-type: inline-size; }
      .cmr-header, .cmr-vehicle-head { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
      .cmr-header-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
      .cmr-title { font-size: 20px; font-weight: 800; letter-spacing: -0.02em; }
      .cmr-subtitle, .cmr-plate, .cmr-row-muted, .cmr-tile-sub { color: var(--secondary-text-color); font-size: 12px; }
      .cmr-mode, .cmr-action { border: 0; border-radius: 999px; padding: 8px 12px; color: var(--primary-text-color); background: color-mix(in srgb, var(--primary-color) 14%, transparent); cursor: pointer; font-weight: 700; }
      .cmr-mode[disabled], .cmr-action[disabled] { opacity: .6; cursor: wait; }
      .cmr-secondary { background: color-mix(in srgb, var(--secondary-text-color) 12%, transparent); }
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
      .cmr-section, .cmr-edit-group, .cmr-add-form { margin-top: 14px; padding: 12px; border-radius: 16px; background: color-mix(in srgb, var(--card-background-color) 92%, var(--primary-color) 8%); }
      .cmr-add-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 14px; }
      .cmr-add-field { display: flex; flex-direction: column; align-items: stretch; gap: 6px; padding: 0; border-top: 0; min-width: 0; }
      .cmr-add-field span { font-size: 12px; line-height: 1.2; }
      .cmr-add-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
      .cmr-message, .cmr-help { margin-top: 10px; color: var(--secondary-text-color); font-size: 12px; line-height: 1.35; }
      .cmr-danger-zone { border: 1px solid color-mix(in srgb, #d64545 35%, var(--divider-color)); }
      .cmr-inactive-zone { border: 1px dashed var(--divider-color); }
      .cmr-inactive-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 10px 0; border-top: 1px solid color-mix(in srgb, var(--divider-color) 70%, transparent); }
      .cmr-inactive-title { font-weight: 800; }
      .cmr-danger { background: color-mix(in srgb, #d64545 20%, transparent); color: var(--primary-text-color); }
      .cmr-section-title { font-size: 13px; font-weight: 900; margin-bottom: 8px; color: var(--primary-text-color); }
      .cmr-row { display: grid; grid-template-columns: 1.35fr .9fr auto auto; gap: 8px; align-items: center; padding: 8px 0; border-top: 1px solid color-mix(in srgb, var(--divider-color) 70%, transparent); }
      .cmr-row:first-of-type { border-top: 0; }
      .cmr-row-label { font-weight: 700; }
      .cmr-row-value { font-weight: 800; }
      .cmr-spec-row { display: grid; grid-template-columns: minmax(92px, .85fr) minmax(0, 1.15fr); gap: 10px; align-items: start; padding: 9px 0; border-top: 1px solid color-mix(in srgb, var(--divider-color) 70%, transparent); }
      .cmr-spec-row:first-of-type { border-top: 0; }
      .cmr-spec-label { font-weight: 800; line-height: 1.25; }
      .cmr-spec-value { font-weight: 800; line-height: 1.3; overflow-wrap: anywhere; }
      .is-good { --cmr-accent: #2e9d58; }
      .is-warn { --cmr-accent: #d99a22; }
      .is-bad { --cmr-accent: #d64545; }
      .is-neutral { --cmr-accent: var(--secondary-text-color); }
      .cmr-tile.is-good, .cmr-tile.is-warn, .cmr-tile.is-bad { border-left: 5px solid var(--cmr-accent); }
      .cmr-row.is-good .cmr-row-value, .cmr-row.is-warn .cmr-row-value, .cmr-row.is-bad .cmr-row-value { color: var(--cmr-accent); }
      .cmr-field { display: grid; grid-template-columns: minmax(105px, 1fr) minmax(120px, 260px); align-items: center; gap: 10px; padding: 7px 0; border-top: 1px solid color-mix(in srgb, var(--divider-color) 70%, transparent); font-weight: 700; }
      .cmr-field span { line-height: 1.25; }
      .cmr-field:first-of-type { border-top: 0; }
      .cmr-field input { width: 100%; min-width: 0; box-sizing: border-box; border: 1px solid var(--divider-color); border-radius: 10px; padding: 8px 10px; background: var(--card-background-color); color: var(--primary-text-color); }
      .cmr-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
      .cmr-empty { margin-top: 14px; color: var(--secondary-text-color); padding: 14px; border: 1px dashed var(--divider-color); border-radius: 14px; }
      @container (max-width: 420px) {
        .cmr-header, .cmr-vehicle-head { align-items: flex-start; }
        .cmr-header-actions { width: 100%; justify-content: flex-start; }
        .cmr-add-grid { grid-template-columns: 1fr; }
        .cmr-field { grid-template-columns: 1fr; }
      }
      @media (max-width: 760px) {
        .cmr-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 6px; }
        .cmr-tile { padding: 8px 5px; min-height: 84px; }
        .cmr-tile-main { font-size: 16px; }
        .cmr-tile-sub { font-size: 11px; }
        .cmr-tile-top { font-size: 9.5px; }
        .cmr-row { grid-template-columns: 1fr; }
        .cmr-spec-row { grid-template-columns: 1fr; gap: 4px; }
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
