class CarManagerRomaniaCard extends HTMLElement {
  static get version() { return "1.0.8"; }
  setConfig(config) {
    this.config = config || {};
    this._editMode = this.config.edit_mode ?? false;
    this._selectedVehicle = this.config.vehicle || null;
    this._showDetails = this.config.show_details ?? false;
    this._expandedVehicles = this._expandedVehicles || new Set();
    this._editingVehicles = this._editingVehicles || new Set();
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
    this._serviceFormOpen = this._serviceFormOpen || new Set();
    this._serviceRecordDrafts = this._serviceRecordDrafts || {};
    this._serviceRecordEditOpen = this._serviceRecordEditOpen || new Set();
    this._serviceRecordEditDrafts = this._serviceRecordEditDrafts || {};
    this._serviceRecordBusy = this._serviceRecordBusy || null;
    this._fuelFormOpen = this._fuelFormOpen || new Set();
    this._fuelReceiptDrafts = this._fuelReceiptDrafts || {};
    this._fuelReceiptBusy = this._fuelReceiptBusy || null;
    this._fuelReceiptMessage = this._fuelReceiptMessage || {};
    this._serviceRecordMessage = this._serviceRecordMessage || {};
    this._inputEditing = this._inputEditing || false;
    this._backupOpen = this._backupOpen || false;
    this._backupBusy = this._backupBusy || null;
    this._backupFilename = this._backupFilename || "car_manager_romania_backup.json";
    this._backupMessage = this._backupMessage || "";
    this._activeTab = this._activeTab || this.config.default_tab || "vehicles";
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
              <button class="cmr-mode" data-action="toggle-backup">Backup</button>
            </div>
          </div>
          ${this._renderTabs()}
          ${this._addVehicleOpen ? this._renderAddVehicleForm() : ""}
          ${this._backupOpen ? this._renderBackupPanel() : ""}
          ${this._activeTab === "costs"
            ? this._renderCostsTab(visibleVehicles)
            : this._activeTab === "fuel"
              ? this._renderFuelTab(visibleVehicles)
              : `${this._anyVehicleEditing() && inactiveVehicles.length ? this._renderInactiveVehicles(inactiveVehicles) : ""}${visibleVehicles.length ? visibleVehicles.map((vehicle) => this._renderVehicle(vehicle)).join("") : this._renderEmpty()}`}
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


  _renderBackupPanel() {
    const filename = this._backupFilename || "car_manager_romania_backup.json";
    const busy = Boolean(this._backupBusy);
    return `
      <section class="cmr-backup-panel">
        <div class="cmr-section-title">Backup și restore</div>
        <div class="cmr-backup-text">
          Exportul se salvează în <strong>/config</strong>, ca să nu expunem VIN, numere de înmatriculare sau observații prin URL public. Îl poți descărca local din File editor / Studio Code.
        </div>
        <label class="cmr-field cmr-backup-field">
          <span>Nume fișier backup</span>
          <input type="text" data-backup-filename value="${this._escape(filename)}" placeholder="car_manager_romania_backup.json">
        </label>
        <div class="cmr-backup-actions">
          <button class="cmr-action" type="button" data-action="backup-export" ${busy ? "disabled" : ""}>${this._backupBusy === "export" ? "Export..." : "Exportă backup"}</button>
          <button class="cmr-action cmr-secondary" type="button" data-action="backup-validate" ${busy ? "disabled" : ""}>${this._backupBusy === "validate" ? "Validare..." : "Validează"}</button>
          <button class="cmr-action cmr-secondary" type="button" data-action="backup-import-dry" ${busy ? "disabled" : ""}>${this._backupBusy === "dry" ? "Simulare..." : "Simulează import"}</button>
          <button class="cmr-action cmr-danger" type="button" data-action="backup-import-real" ${busy ? "disabled" : ""}>${this._backupBusy === "import" ? "Import..." : "Importă merge"}</button>
        </div>
        <div class="cmr-backup-note">Importul disponibil este momentan doar <strong>merge</strong>: adaugă/actualizează datele din backup, fără să șteargă date existente.</div>
        ${this._backupMessage ? `<div class="cmr-message">${this._escape(this._backupMessage)}</div>` : ""}
      </section>
    `;
  }


  _renderTabs() {
    const active = this._activeTab || "vehicles";
    return `
      <div class="cmr-tabs" role="tablist">
        <button class="cmr-tab ${active === "vehicles" ? "is-active" : ""}" data-action="set-tab" data-tab="vehicles" type="button">Autovehicule</button>
        <button class="cmr-tab ${active === "costs" ? "is-active" : ""}" data-action="set-tab" data-tab="costs" type="button">Costuri</button>
        <button class="cmr-tab ${active === "fuel" ? "is-active" : ""}" data-action="set-tab" data-tab="fuel" type="button">Combustibil</button>
      </div>
    `;
  }

  _renderCostsTab(vehicles) {
    if (!vehicles.length) return this._renderEmpty();

    const summaries = vehicles.map((vehicle) => this._costSummaryForVehicle(vehicle));
    const totalAnnual = summaries.reduce((sum, item) => sum + item.annual, 0);
    const total30 = summaries.reduce((sum, item) => sum + item.upcoming30, 0);
    const total90 = summaries.reduce((sum, item) => sum + item.upcoming90, 0);
    const allUpcoming90 = summaries.flatMap((summary) => summary.items90.map((item) => ({ ...item, vehicle_label: summary.label })));
    const allUpcoming30 = allUpcoming90.filter((item) => this._toNumber(item.days_remaining) <= 30);
    const byType = this._groupCostItemsByType(allUpcoming90);

    return `
      <section class="cmr-costs-panel">
        <div class="cmr-section-title">Costuri</div>
        <div class="cmr-cost-summary-grid">
          ${this._renderCostSummaryCard("Costuri anul curent", totalAnnual, "Din istoricul intervențiilor salvate")}
          ${this._renderCostSummaryCard("Următoarele 30 zile", total30, `${allUpcoming30.length} cheltuieli estimate`)}
          ${this._renderCostSummaryCard("Următoarele 90 zile", total90, `${allUpcoming90.length} cheltuieli estimate`)}
        </div>
        <div class="cmr-cost-section">
          <div class="cmr-section-title">Defalcare pe autovehicul</div>
          <div class="cmr-cost-table">
            <div class="cmr-cost-table-row cmr-cost-table-head">
              <span>Autovehicul</span><span>An curent</span><span>30 zile</span><span>90 zile</span>
            </div>
            ${summaries.map((summary) => `
              <div class="cmr-cost-table-row">
                <span><strong>${this._escape(summary.label)}</strong><small>${this._escape(summary.plate || "")}</small></span>
                <span>${this._formatMoney(summary.annual)}</span>
                <span>${this._formatMoney(summary.upcoming30)}</span>
                <span>${this._formatMoney(summary.upcoming90)}</span>
              </div>
            `).join("")}
          </div>
        </div>
        <div class="cmr-cost-section">
          <div class="cmr-section-title">Defalcare pe tip, următoarele 90 zile</div>
          ${byType.length ? `
            <div class="cmr-cost-chips">
              ${byType.map((item) => `<div class="cmr-cost-chip"><span>${this._escape(item.label)}</span><strong>${this._formatMoney(item.total)}</strong></div>`).join("")}
            </div>
          ` : `<div class="cmr-history-empty">Nu există cheltuieli estimate în următoarele 90 de zile.</div>`}
        </div>
        <div class="cmr-cost-section">
          <div class="cmr-section-head">
            <div class="cmr-section-title">Cheltuieli estimate care urmează</div>
          </div>
          ${this._renderUpcomingCostItems(allUpcoming90)}
        </div>
      </section>
    `;
  }


  _renderFuelTab(vehicles) {
    if (!vehicles.length) return this._renderEmpty();

    const summaries = vehicles.map((vehicle) => this._fuelSummaryForVehicle(vehicle));
    const totalYear = summaries.reduce((sum, item) => sum + item.yearCost, 0);
    const totalMonth = summaries.reduce((sum, item) => sum + item.monthCost, 0);
    const receipts = summaries.flatMap((summary) => summary.receipts.map((receipt) => ({ ...receipt, vehicle_label: summary.label })));

    return `
      <section class="cmr-costs-panel">
        <div class="cmr-section-title">Combustibil</div>
        <div class="cmr-cost-summary-grid">
          ${this._renderCostSummaryCard("Combustibil anul curent", totalYear, "Din bonurile salvate")}
          ${this._renderCostSummaryCard("Combustibil luna curentă", totalMonth, "Din bonurile salvate")}
          ${this._renderCostSummaryCard("Bonuri salvate", `${receipts.length}`, "Total alimentări afișate")}
        </div>
        ${summaries.map((summary) => this._renderFuelVehiclePanel(summary)).join("")}
      </section>
    `;
  }

  _fuelSummaryForVehicle(vehicle) {
    const attrs = this._vehicleStatusAttributes(vehicle);
    const yearSensor = this._findSensorByName(vehicle, ["combustibil", "anul", "curent"]);
    const monthSensor = this._findSensorByName(vehicle, ["combustibil", "luna", "curenta"]);
    const consumptionSensor = this._findSensorByName(vehicle, ["consum", "mediu", "combustibil"]);
    const receipts = Array.isArray(attrs.fuel_receipts) ? attrs.fuel_receipts : [];
    const intervals = Array.isArray(attrs.fuel_consumption_intervals) ? attrs.fuel_consumption_intervals : [];
    return {
      vehicle,
      key: vehicle.vehicle_id || vehicle.key || vehicle.label,
      label: vehicle.label || "Autovehicul",
      plate: vehicle.plate || "",
      yearCost: this._toNumber(this._entityValue(yearSensor)),
      monthCost: this._toNumber(this._entityValue(monthSensor)),
      averageConsumption: this._entityValue(consumptionSensor),
      receipts,
      intervals,
    };
  }

  _renderFuelVehiclePanel(summary) {
    const open = this._fuelFormOpen.has(summary.key);
    const message = this._fuelReceiptMessage[summary.key] || "";
    const latestInterval = summary.intervals?.[0];
    return `
      <div class="cmr-cost-section">
        <div class="cmr-section-head">
          <div>
            <div class="cmr-section-title">${this._escape(summary.label)}</div>
            <div class="cmr-row-muted">${this._escape(summary.plate || "")}</div>
          </div>
          <button class="cmr-mini-action" type="button" data-action="toggle-fuel-form" data-vehicle="${this._escape(summary.key)}">${open ? "Închide" : "Adaugă bon"}</button>
        </div>
        <div class="cmr-cost-summary-grid cmr-fuel-summary-grid">
          ${this._renderCostSummaryCard("An curent", summary.yearCost, "combustibil")}
          ${this._renderCostSummaryCard("Luna curentă", summary.monthCost, "combustibil")}
          ${this._renderCostSummaryCard("Consum mediu", summary.averageConsumption && summary.averageConsumption !== "unknown" && summary.averageConsumption !== "unavailable" ? `${summary.averageConsumption} L/100 km` : "—", latestInterval ? `${latestInterval.distance_km} km · ${latestInterval.liters} L` : "necalculat")}
        </div>
        ${open ? this._renderFuelReceiptForm(summary.vehicle) : ""}
        ${message ? `<div class="cmr-message">${this._escape(message)}</div>` : ""}
        ${this._renderFuelReceipts(summary)}
      </div>
    `;
  }

  _renderFuelMini(vehicle) {
    const yearSensor = this._findSensorByName(vehicle, ["combustibil", "anul", "curent"]);
    const monthSensor = this._findSensorByName(vehicle, ["combustibil", "luna", "curenta"]);
    const consumptionSensor = this._findSensorByName(vehicle, ["consum", "mediu", "combustibil"]);
    if (!yearSensor && !monthSensor && !consumptionSensor) return "";
    return `<div class="cmr-section"><div class="cmr-section-title">Combustibil</div>
      ${this._renderRow("An curent", this._formatMoney(this._toNumber(this._entityValue(yearSensor))), "", "", "")}
      ${this._renderRow("Luna curentă", this._formatMoney(this._toNumber(this._entityValue(monthSensor))), "", "", "")}
      ${this._renderRow("Consum mediu", this._entityValue(consumptionSensor) ? `${this._entityValue(consumptionSensor)} L/100 km` : "—", "", "", "")}
    </div>`;
  }

  _renderFuelReceiptForm(vehicle) {
    const vehicleKey = vehicle.vehicle_id || vehicle.key || vehicle.label || "";
    const draft = this._fuelReceiptDrafts[vehicleKey] || {};
    const today = new Date().toISOString().slice(0, 10);
    const fuelProfile = this._vehicleFuelProfile(vehicle);
    const fuelOptions = this._fuelTypeOptions(fuelProfile, draft.fuel_type || "");
    return `
      <form class="cmr-history-form" data-form="fuel-receipt" data-vehicle="${this._escape(vehicleKey)}" data-vehicle-ref="${this._escape(vehicle.vehicle_id || vehicle.plate || vehicle.label || vehicle.key || "")}">
        <div class="cmr-add-grid">
          <label class="cmr-field"><span>Data alimentării</span><input type="date" name="date" value="${this._escape(draft.date || today)}"></label>
          <label class="cmr-field"><span>Kilometraj bord</span><input type="number" name="km" min="1" step="1" required value="${this._escape(draft.km || this._extractSummary(vehicle).km || "")}"></label>
          <label class="cmr-field"><span>Tip combustibil</span><select name="fuel_type" required>${fuelOptions}</select></label>
          <label class="cmr-field"><span>Litri / kWh</span><input type="number" name="quantity" min="0.001" step="0.001" required value="${this._escape(draft.quantity || "")}"></label>
          <label class="cmr-field"><span>Valoare bon</span><input type="number" name="total_cost" min="0.01" step="0.01" required value="${this._escape(draft.total_cost || "")}"></label>
          <label class="cmr-field"><span>Stație</span><input type="text" name="station" value="${this._escape(draft.station || "")}" placeholder="opțional"></label>
        </div>
        <label class="cmr-check"><input type="checkbox" name="full_tank" ${draft.full_tank === false ? "" : "checked"}> Plin făcut</label>
        <label class="cmr-field"><span>Observații</span><textarea name="notes" rows="2">${this._escape(draft.notes || "")}</textarea></label>
        <div class="cmr-add-actions">
          <button class="cmr-action" type="submit" ${this._fuelReceiptBusy === vehicleKey ? "disabled" : ""}>${this._fuelReceiptBusy === vehicleKey ? "Se salvează..." : "Salvează bon"}</button>
        </div>
      </form>
    `;
  }

  _renderFuelReceipts(summary) {
    const receipts = Array.isArray(summary.receipts) ? summary.receipts : [];
    if (!receipts.length) return `<div class="cmr-history-empty">Nu există bonuri de combustibil salvate încă.</div>`;
    return `<div class="cmr-cost-list">${receipts.slice(0, 8).map((receipt) => `
      <div class="cmr-cost-item">
        <div class="cmr-cost-item-main">
          <div class="cmr-cost-item-title">${this._escape(receipt.fuel_type_label || "Combustibil")} <span>${this._escape(receipt.date || "")}</span></div>
          <div class="cmr-row-muted">${this._escape([receipt.km ? `${receipt.km} km` : "", receipt.quantity ? `${receipt.quantity} ${receipt.unit || "L"}` : "", receipt.unit_price ? `${receipt.unit_price} RON/${receipt.unit || "L"}` : "", receipt.station || ""].filter(Boolean).join(" · "))}</div>
        </div>
        <div class="cmr-cost-item-value">${this._formatMoney(receipt.total_cost)}</div>
      </div>
    `).join("")}</div>`;
  }

  _vehicleFuelProfile(vehicle) {
    const entity = vehicle.entities.find((item) => item.entityId?.startsWith("text.") && this._normalize(this._friendly(item)).includes("motorizare"));
    const value = (entity?.stateObj?.state || "diesel").toString();
    return value && value !== "unknown" && value !== "unavailable" ? value : "diesel";
  }

  _fuelProfileOptions(selected) {
    const options = [
      ["gasoline", "Benzină"], ["diesel", "Motorină"], ["lpg", "GPL"], ["electric", "Electric"],
      ["hybrid_gasoline", "Hibrid benzină"], ["hybrid_diesel", "Hibrid motorină"],
      ["phev_gasoline", "Plug-in hybrid benzină"], ["phev_diesel", "Plug-in hybrid motorină"],
    ];
    return options.map(([value, label]) => `<option value="${value}" ${value === selected ? "selected" : ""}>${label}</option>`).join("");
  }

  _fuelTypeOptions(profile, selected) {
    const byProfile = {
      gasoline: [["gasoline_standard", "Benzină standard"], ["gasoline_premium", "Benzină premium"]],
      diesel: [["diesel_standard", "Motorină standard"], ["diesel_premium", "Motorină premium"]],
      lpg: [["lpg", "GPL"], ["gasoline_standard", "Benzină standard"], ["gasoline_premium", "Benzină premium"]],
      electric: [["electric_charge", "Încărcare electrică"]],
      hybrid_gasoline: [["gasoline_standard", "Benzină standard"], ["gasoline_premium", "Benzină premium"]],
      hybrid_diesel: [["diesel_standard", "Motorină standard"], ["diesel_premium", "Motorină premium"]],
      phev_gasoline: [["gasoline_standard", "Benzină standard"], ["gasoline_premium", "Benzină premium"], ["electric_charge", "Încărcare electrică"]],
      phev_diesel: [["diesel_standard", "Motorină standard"], ["diesel_premium", "Motorină premium"], ["electric_charge", "Încărcare electrică"]],
    };
    const options = byProfile[profile] || byProfile.diesel;
    const selectedValue = selected || options[0][0];
    return options.map(([value, label]) => `<option value="${value}" ${value === selectedValue ? "selected" : ""}>${label}</option>`).join("");
  }

  _renderCostSummaryCard(title, amount, subtitle) {
    const displayValue = typeof amount === "string" ? amount : this._formatMoney(amount);
    return `
      <div class="cmr-cost-card">
        <div class="cmr-cost-title">${this._escape(title)}</div>
        <div class="cmr-cost-value">${this._escape(displayValue)}</div>
        <div class="cmr-row-muted">${this._escape(subtitle || "")}</div>
      </div>
    `;
  }

  _costSummaryForVehicle(vehicle) {
    const annualSensor = this._findSensorByName(vehicle, ["costuri", "anul", "curent"]);
    const upcoming30Sensor = this._findSensorByName(vehicle, ["cheltuieli", "urmatoarele", "30", "zile"]);
    const upcoming90Sensor = this._findSensorByName(vehicle, ["cheltuieli", "urmatoarele", "90", "zile"]);
    const items30 = this._costItemsFromSensor(upcoming30Sensor);
    const items90 = this._costItemsFromSensor(upcoming90Sensor);

    return {
      vehicle,
      label: vehicle.label || "Autovehicul",
      plate: vehicle.plate || "",
      annual: this._toNumber(this._entityValue(annualSensor)),
      upcoming30: this._toNumber(this._entityValue(upcoming30Sensor)),
      upcoming90: this._toNumber(this._entityValue(upcoming90Sensor)),
      items30,
      items90,
    };
  }

  _costItemsFromSensor(sensor) {
    const attrs = sensor?.stateObj?.attributes || {};
    const items = Array.isArray(attrs.items_with_cost) ? attrs.items_with_cost : Array.isArray(attrs.items) ? attrs.items.filter((item) => this._toNumber(item?.cost) > 0) : [];
    return items
      .filter((item) => item && typeof item === "object" && this._toNumber(item.cost) > 0)
      .map((item) => ({
        category: item.category || "other",
        key: item.key || "",
        label: item.label || "Cheltuială",
        status: item.status || "",
        days_remaining: this._toNumber(item.days_remaining),
        km_remaining: item.km_remaining,
        due_date: item.due_date || "",
        cost: this._toNumber(item.cost),
      }))
      .sort((a, b) => (a.days_remaining - b.days_remaining) || a.label.localeCompare(b.label, "ro"));
  }

  _groupCostItemsByType(items) {
    const groups = new Map();
    for (const item of items) {
      const key = `${item.category || "other"}:${item.key || item.label || "other"}`;
      const label = item.label || this._costCategoryLabel(item.category);
      const existing = groups.get(key) || { label, total: 0 };
      existing.total += this._toNumber(item.cost);
      groups.set(key, existing);
    }
    return [...groups.values()].sort((a, b) => b.total - a.total || a.label.localeCompare(b.label, "ro"));
  }

  _renderUpcomingCostItems(items) {
    if (!items.length) return `<div class="cmr-history-empty">Nu există cheltuieli estimate configurate în următoarele 90 de zile.</div>`;

    return `
      <div class="cmr-cost-list">
        ${items.map((item) => `
          <div class="cmr-cost-item">
            <div class="cmr-cost-item-main">
              <div class="cmr-cost-item-title">${this._escape(item.label || "Cheltuială")} <span>${this._escape(item.vehicle_label || "")}</span></div>
              <div class="cmr-row-muted">${this._escape(this._costItemMeta(item))}</div>
            </div>
            <div class="cmr-cost-item-value">${this._formatMoney(item.cost)}</div>
          </div>
        `).join("")}
      </div>
    `;
  }

  _costItemMeta(item) {
    const parts = [];
    const days = this._toNumber(item.days_remaining);
    if (Number.isFinite(days)) parts.push(days <= 0 ? "scadent" : `în ${days} zile`);
    if (item.due_date) parts.push(item.due_date);
    if (item.km_remaining !== null && item.km_remaining !== undefined && item.km_remaining !== "") parts.push(`${item.km_remaining} km rămași`);
    if (item.status) parts.push(item.status);
    return parts.join(" · ");
  }

  _toNumber(value) {
    const number = Number(value ?? 0);
    return Number.isFinite(number) ? number : 0;
  }

  _formatMoney(value) {
    const amount = this._toNumber(value);
    return `${amount.toLocaleString("ro-RO", { minimumFractionDigits: amount % 1 ? 2 : 0, maximumFractionDigits: 2 })} RON`;
  }

  _renderVehicle(vehicle) {
    const summary = this._extractSummary(vehicle);
    const editing = this._isVehicleEditing(vehicle);

    return `
      <section class="cmr-vehicle">
        <div class="cmr-vehicle-head">
          <div>
            <div class="cmr-vehicle-title">${this._escape(vehicle.label)}</div>
            <div class="cmr-plate">${this._escape(vehicle.plate || "Număr neconfigurat")}${vehicle.vin ? ` · VIN: ${this._escape(vehicle.vin)}` : ""}</div>
          </div>
          <div class="cmr-vehicle-head-actions">
            <div class="cmr-km">${this._escape(summary.km || "—")} km</div>
            <button class="cmr-mode cmr-vehicle-edit-button" data-action="toggle-vehicle-edit" data-vehicle="${this._escape(vehicle.key)}">${editing ? "Afișare" : "Editare"}</button>
          </div>
        </div>
        ${editing ? this._renderEdit(vehicle) : this._renderDashboard(vehicle, summary)}
      </section>
    `;
  }

  _renderDashboard(vehicle, summary) {
    const expanded = this._showDetails || this._expandedVehicles.has(vehicle.key);
    return `
      ${this._renderOverallSummary(vehicle)}
      <div class="cmr-grid">
        ${this._renderTile("Revizie", summary.serviceStatus, summary.serviceDays, summary.serviceKm, "mdi:wrench-clock")}
        ${this._renderTile("RCA", summary.rcaStatus, summary.rcaDays, summary.rcaExpiry, "mdi:shield-check")}
        ${this._shouldShowCascoTile(summary) ? this._renderTile("CASCO", summary.cascoStatus, summary.cascoDays, summary.cascoExpiry, "mdi:shield-star") : ""}
        ${this._renderTile("ITP", summary.itpStatus, summary.itpDays, summary.itpExpiry, "mdi:clipboard-check")}
        ${this._renderTile("Rovinietă", summary.rovinietaStatus, summary.rovinietaDays, summary.rovinietaExpiry, "mdi:road-variant")}
      </div>
      <div class="cmr-details-bar">
        <button class="cmr-details-button" data-action="toggle-details" data-vehicle="${this._escape(vehicle.key)}">
          ${expanded ? "Ascunde detalii" : "Detalii"}
        </button>
      </div>
      ${expanded ? `<div class="cmr-details">${this._renderMaintenance(vehicle)}${this._renderFuelMini(vehicle)}${this._renderConsumables(vehicle)}${this._renderServiceHistory(vehicle)}${this._showDetails ? this._renderRovinietaDetails(vehicle) : ""}</div>` : ""}
    `;
  }

  _renderOverallSummary(vehicle) {
    const attrs = this._vehicleStatusAttributes(vehicle);
    const overallStatus = attrs.overall_status || attrs.overall_status_label || "ok";
    const overallLabel = attrs.overall_status_label || overallStatus || "OK";
    const criticalItems = Array.isArray(attrs.critical_items) ? attrs.critical_items : [];
    const warningItems = Array.isArray(attrs.warning_items) ? attrs.warning_items : [];
    const okItems = Array.isArray(attrs.ok_items) ? attrs.ok_items : [];
    const mainItems = [...criticalItems, ...warningItems].slice(0, 4);
    const stateClass = this._statusClass(overallStatus);

    const itemsHtml = mainItems.length
      ? mainItems.map((item) => this._renderOverallItem(item, vehicle, overallStatus)).join("")
      : `<div class="cmr-overall-ok">Nu sunt probleme critice sau avertizări. ${okItems.length ? `${okItems.length} elemente sunt în regulă.` : ""}</div>`;

    const countText = criticalItems.length
      ? `${criticalItems.length} critic${criticalItems.length === 1 ? "" : "e"}${warningItems.length ? ` · ${warningItems.length} atenționări` : ""}`
      : warningItems.length
        ? `${warningItems.length} atenționări`
        : "totul pare în regulă";

    return `
      <div class="cmr-overall ${stateClass}">
        <div class="cmr-overall-head">
          <div>
            <div class="cmr-overall-title">Stare generală</div>
            <div class="cmr-row-muted">${this._escape(countText)}</div>
          </div>
          <div class="cmr-overall-badge">${this._escape(overallLabel)}</div>
        </div>
        <div class="cmr-overall-list">${itemsHtml}</div>
      </div>
    `;
  }


  _renderOverallItem(item, vehicle, overallStatus) {
    const vehicleRef = vehicle.vehicle_id || vehicle.plate || vehicle.label || vehicle.key || "";
    const canIgnoreCasco = item?.category === "legal" && item?.key === "casco" && item?.can_ignore;
    const action = canIgnoreCasco
      ? `<button class="cmr-mini-action cmr-secondary cmr-overall-action" data-action="ignore-casco" data-vehicle-id="${this._escape(vehicleRef)}">Nu folosesc CASCO</button>`
      : "";

    return `
      <div class="cmr-overall-item ${this._statusClass(item.status || item.summary || overallStatus)}">
        <span class="cmr-overall-dot"></span>
        <span>${this._escape(item.label || "Element")}:</span>
        <strong>${this._escape(item.summary || item.status || "neconfigurat")}</strong>
        ${action}
      </div>
    `;
  }

  _vehicleStatusAttributes(vehicle) {
    const statusEntity = vehicle.entities.find((entity) => {
      const attrs = entity.stateObj?.attributes || {};
      return entity.entityId.startsWith("sensor.") && attrs.vehicle_id && (attrs.overall_status || Array.isArray(attrs.critical_items));
    });

    if (statusEntity) return statusEntity.stateObj.attributes || {};

    const fallbackEntity = vehicle.entities.find((entity) => {
      const attrs = entity.stateObj?.attributes || {};
      return entity.entityId.startsWith("sensor.") && attrs.vehicle_id;
    });

    return fallbackEntity?.stateObj?.attributes || {};
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
      this._shouldShowCascoTile(summary) ? this._renderRow("CASCO expiră la", summary.cascoExpiry, summary.cascoDays, summary.cascoStatus, this._statusClass(summary.cascoStatus || summary.cascoDays)) : "",
      this._renderRow("ITP expiră la", summary.itpExpiry, summary.itpDays, summary.itpStatus, this._statusClass(summary.itpStatus || summary.itpDays)),
      this._renderRow("Rovinietă expiră la", summary.rovinietaExpiry, summary.rovinietaDays, summary.rovinietaStatus, this._statusClass(summary.rovinietaStatus || summary.rovinietaDays)),
    ].filter(Boolean).join("");

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

  _renderServiceHistory(vehicle) {
    let records = [];
    try {
      const statusEntity = vehicle.entities.find((entity) => {
        const attrs = entity.stateObj?.attributes || {};
        return entity.entityId.startsWith("sensor.") && Array.isArray(attrs.service_history);
      });
      const rawRecords = statusEntity?.stateObj?.attributes?.service_history;
      records = Array.isArray(rawRecords) ? rawRecords.filter((record) => record && typeof record === "object") : [];
    } catch (error) {
      console.warn("Car Manager România: nu am putut citi istoricul intervențiilor", error);
      records = [];
    }

    const vehicleKey = vehicle.vehicle_id || vehicle.vin || vehicle.plate || vehicle.key || vehicle.label || "";
    const open = this._serviceFormOpen.has(vehicleKey);
    const message = this._serviceRecordMessage[vehicleKey] || "";

    let rows = "";
    try {
      rows = records.length
        ? records.slice(0, 5).map((record) => this._renderServiceHistoryRow(record, vehicleKey)).join("")
        : `<div class="cmr-history-empty">Nu există intervenții salvate încă.</div>`;
    } catch (error) {
      console.warn("Car Manager România: nu am putut afișa rândurile din istoricul intervențiilor", error);
      rows = `<div class="cmr-history-empty">Istoricul există, dar nu a putut fi afișat. Verifică jurnalul Home Assistant.</div>`;
    }

    return `
      <div class="cmr-section cmr-history-section">
        <div class="cmr-section-head">
          <div class="cmr-section-title">Istoric intervenții</div>
          <button class="cmr-mini-action" data-action="toggle-service-form" data-vehicle="${this._escape(vehicleKey)}">
            ${open ? "Închide" : "Adaugă"}
          </button>
        </div>
        ${open ? this._renderServiceRecordForm(vehicle) : ""}
        ${message ? `<div class="cmr-message">${this._escape(message)}</div>` : ""}
        <div class="cmr-history-list">${rows}</div>
      </div>
    `;
  }

  _renderServiceHistoryRow(record, vehicleKey) {
    const recordId = record.record_id || "";
    const title = record.title || record.record_type_label || this._recordTypeLabel(record.record_type);
    const meta = [
      record.date || "fără dată",
      record.km ? `${record.km} km` : "",
      record.service_name || "",
      record.cost ? `${record.cost} lei` : "",
    ].filter(Boolean).join(" · ");
    const restored = Boolean(record.restored);
    const canRestore = recordId && record.update_maintenance && !restored;
    const editOpen = recordId && this._serviceRecordEditOpen.has(recordId);
    const statusBadge = restored
      ? `<span class="cmr-history-badge cmr-history-badge-restored">restaurată</span>`
      : record.update_maintenance
        ? `<span class="cmr-history-badge cmr-history-badge-active">aplicată</span>`
        : `<span class="cmr-history-badge cmr-history-badge-info">istoric</span>`;
    const restoreButton = canRestore
      ? `<button class="cmr-mini-action cmr-secondary" data-action="restore-service-record" data-record-id="${this._escape(recordId)}" data-vehicle="${this._escape(vehicleKey)}">Restore</button>`
      : "";
    const editButton = recordId
      ? `<button class="cmr-mini-action cmr-secondary" data-action="toggle-edit-service-record" data-record-id="${this._escape(recordId)}" data-vehicle="${this._escape(vehicleKey)}">${editOpen ? "Închide" : "Editează"}</button>`
      : "";
    const deleteButton = recordId
      ? `<button class="cmr-mini-action cmr-danger" data-action="delete-service-record" data-record-id="${this._escape(recordId)}" data-vehicle="${this._escape(vehicleKey)}" data-updates-maintenance="${record.update_maintenance ? "1" : "0"}" data-restored="${restored ? "1" : "0"}">Șterge</button>`
      : "";

    return `
      <div class="cmr-history-row ${restored ? "cmr-history-row-restored" : ""}">
        <div class="cmr-history-main">
          <div class="cmr-history-title">${this._escape(title)} ${statusBadge}</div>
          <div class="cmr-row-muted">${this._escape(meta || this._recordTypeLabel(record.record_type))}</div>
          ${record.notes ? `<div class="cmr-history-notes">${this._escape(record.notes)}</div>` : ""}
          ${editOpen ? this._renderServiceRecordEditForm(record, vehicleKey) : ""}
        </div>
        <div class="cmr-history-actions">
          ${restoreButton}
          ${editButton}
          ${deleteButton}
        </div>
      </div>
    `;
  }

  _renderServiceRecordEditForm(record, vehicleKey) {
    const recordId = record.record_id || "";
    const draft = this._serviceRecordEditDrafts[recordId] || {};
    const busy = this._serviceRecordBusy === recordId;
    return `
      <form class="cmr-service-form cmr-history-edit-form" data-form="service-record-edit" data-record-id="${this._escape(recordId)}" data-vehicle="${this._escape(vehicleKey)}">
        <div class="cmr-help">Editarea modifică doar titlul, service-ul, costul, documentul și observațiile. Data, kilometrajul și tipul intervenției rămân neschimbate.</div>
        <div class="cmr-service-grid">
          <label class="cmr-field cmr-service-wide">
            <span>Titlu</span>
            <input type="text" name="title" value="${this._escape(draft.title ?? record.title ?? "")}">
          </label>
          <label class="cmr-field">
            <span>Service / furnizor</span>
            <input type="text" name="service_name" value="${this._escape(draft.service_name ?? record.service_name ?? "")}">
          </label>
          <label class="cmr-field">
            <span>Cost</span>
            <input type="number" name="cost" min="0" step="0.01" value="${this._escape(draft.cost ?? record.cost ?? "0")}">
          </label>
          <label class="cmr-field">
            <span>Nr. document</span>
            <input type="text" name="invoice_number" value="${this._escape(draft.invoice_number ?? record.invoice_number ?? "")}">
          </label>
          <label class="cmr-field cmr-service-wide">
            <span>Observații</span>
            <textarea name="notes" rows="2">${this._escape(draft.notes ?? record.notes ?? "")}</textarea>
          </label>
        </div>
        <div class="cmr-add-actions">
          <button class="cmr-action" type="submit" ${busy ? "disabled" : ""}>${busy ? "Se salvează..." : "Salvează modificările"}</button>
          <button class="cmr-action cmr-secondary" type="button" data-action="cancel-edit-service-record" data-record-id="${this._escape(recordId)}">Renunță</button>
        </div>
      </form>
    `;
  }

  _renderServiceRecordForm(vehicle) {
    const vehicleKey = vehicle.vehicle_id || vehicle.key;
    const draft = this._serviceRecordDrafts[vehicleKey] || {};
    const summary = this._extractSummary(vehicle);
    const today = new Date().toISOString().slice(0, 10);
    const busy = this._serviceRecordBusy === vehicleKey;
    const km = draft.km ?? (summary.km && summary.km !== "—" ? summary.km : "0");

    return `
      <form class="cmr-service-form" data-form="service-record" data-vehicle="${this._escape(vehicleKey)}" data-vehicle-ref="${this._escape(vehicle.vehicle_id || vehicle.vin || vehicle.plate || vehicle.label)}">
        <div class="cmr-service-grid">
          <label class="cmr-field">
            <span>Tip intervenție</span>
            <select name="record_type">
              ${this._recordTypeOptions(draft.record_type || "service")}
            </select>
          </label>
          <label class="cmr-field">
            <span>Data</span>
            <input type="date" name="date" value="${this._escape(draft.date || today)}">
          </label>
          <label class="cmr-field">
            <span>Kilometraj</span>
            <input type="number" name="km" min="0" step="1" value="${this._escape(km)}">
          </label>
          <label class="cmr-field">
            <span>Cost</span>
            <input type="number" name="cost" min="0" step="0.01" value="${this._escape(draft.cost || "0")}">
          </label>
          <label class="cmr-field cmr-service-wide">
            <span>Titlu</span>
            <input type="text" name="title" placeholder="ex. Schimb ulei și filtre" value="${this._escape(draft.title || "")}">
          </label>
          <label class="cmr-field">
            <span>Service / furnizor</span>
            <input type="text" name="service_name" value="${this._escape(draft.service_name || "")}">
          </label>
          <label class="cmr-field">
            <span>Nr. document</span>
            <input type="text" name="invoice_number" value="${this._escape(draft.invoice_number || "")}">
          </label>
          <label class="cmr-field cmr-service-wide">
            <span>Observații</span>
            <textarea name="notes" rows="2">${this._escape(draft.notes || "")}</textarea>
          </label>
        </div>
        <label class="cmr-check">
          <input type="checkbox" name="update_maintenance" ${draft.update_maintenance === false ? "" : "checked"}>
          <span>Actualizează automat mentenanța pentru tipurile mecanice</span>
        </label>
        <div class="cmr-add-actions">
          <button class="cmr-action" type="submit" ${busy ? "disabled" : ""}>${busy ? "Se salvează..." : "Salvează intervenția"}</button>
        </div>
      </form>
    `;
  }

  _recordTypeOptions(selected) {
    const options = [
      ["service", "Revizie generală"],
      ["gearbox_oil", "Ulei cutie viteze"],
      ["timing_belt", "Distribuție"],
      ["brake_fluid", "Lichid frână"],
      ["coolant", "Lichid antigel"],
      ["rca", "RCA"],
      ["casco", "CASCO"],
      ["itp", "ITP"],
      ["rovinieta", "Rovinietă"],
      ["custom", "Altă intervenție"],
    ];
    return options.map(([value, label]) => `<option value="${value}" ${value === selected ? "selected" : ""}>${label}</option>`).join("");
  }

  _recordTypeLabel(value) {
    const labels = {
      service: "Revizie generală",
      gearbox_oil: "Ulei cutie viteze",
      timing_belt: "Distribuție",
      brake_fluid: "Lichid frână",
      coolant: "Lichid antigel",
      rca: "RCA",
      casco: "CASCO",
      itp: "ITP",
      rovinieta: "Rovinietă",
      custom: "Altă intervenție",
    };
    return labels[value] || value || "Intervenție";
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
    const editable = this._dedupeEditableEntities(
      vehicle.entities.filter(({ entityId }) => entityId.startsWith("number.") || entityId.startsWith("date.") || entityId.startsWith("text."))
    ).filter((entity) => this._isEditableField(entity));

    const groups = [
      { title: "Date autovehicul", test: (e) => this._isVehicleEditField(e) || this._isFuelProfileEditField(e) },
      { title: "Revizie generală", test: (e) => this._isMaintenanceEditField(e, ["revizie"]) },
      { title: "Ulei cutie viteze", test: (e) => this._isMaintenanceEditField(e, ["ulei cutie"]) },
      { title: "Distribuție", test: (e) => this._isMaintenanceEditField(e, ["distribu"]) },
      { title: "Lichid frână", test: (e) => this._isMaintenanceEditField(e, ["lichid fr"]) },
      { title: "Lichid antigel", test: (e) => this._isMaintenanceEditField(e, ["antigel"]) },
      { title: "RCA", test: (e) => this._isLegalEditField(e, "rca") },
      { title: "CASCO", test: (e) => this._isLegalEditField(e, "casco") },
      { title: "ITP", test: (e) => this._isLegalEditField(e, "itp") },
      { title: "Rovinietă", test: (e) => this._isLegalEditField(e, "rovinieta") },
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
    const cascoOption = this._renderCascoOption(vehicle);

    return `${cascoOption}${content || this._renderEmpty()}${buttons ? `<div class="cmr-actions">${buttons}</div>` : ""}${admin}`;
  }

  _renderCascoOption(vehicle) {
    if (!this._isCascoIgnored(vehicle)) return "";

    const vehicleRef = vehicle.vehicle_id || vehicle.plate || vehicle.label || vehicle.key || "";
    return `
      <div class="cmr-edit-group cmr-option-panel">
        <div class="cmr-section-title">CASCO</div>
        <div class="cmr-help">CASCO este marcat ca nefolosit pentru acest autovehicul.</div>
        <button class="cmr-action" type="button" data-action="reactivate-casco" data-vehicle-id="${this._escape(vehicleRef)}">Reactivează CASCO</button>
      </div>
    `;
  }

  _isCascoIgnored(vehicle) {
    return vehicle.entities.some((entity) => {
      const attrs = entity.stateObj?.attributes || {};
      const name = this._normalize(this._friendly(entity));
      return name.includes("casco") && (attrs.ignored === true || attrs.legal_ignored === true);
    });
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

  _dedupeEditableEntities(entities) {
    const best = new Map();

    for (const entity of entities) {
      const key = this._editableSemanticKey(entity);
      const existing = best.get(key);
      if (!existing || this._editableEntityScore(entity) > this._editableEntityScore(existing)) {
        best.set(key, entity);
      }
    }

    return [...best.values()];
  }

  _editableSemanticKey(entity) {
    const domain = (entity.entityId || "").split(".")[0] || "entity";
    const friendly = this._friendly(entity);
    const name = this._normalize(friendly).replace(/\s+/g, " ").trim();
    const label = this._normalize(this._fieldLabel(friendly)).replace(/\s+/g, " ").trim();

    const legalTypes = ["rca", "casco", "itp", "rovinieta"];
    for (const legalType of legalTypes) {
      if (name.includes(legalType)) {
        const legalField = this._canonicalEditableField(label, [
          ["cost", ["cost estimat"]],
          ["start", ["incepe la"]],
          ["expiry", ["expira la"]],
          ["insurer", ["asigurator"]],
          ["policy", ["numar polita"]],
          ["coverage", ["acoperire"]],
          ["station", ["statie"]],
          ["report", ["numar raport"]],
          ["notes", ["observatii"]],
        ]);
        if (legalField) return `${domain}:legal:${legalType}:${legalField}`;
      }
    }

    const maintenanceTypes = [
      ["service", ["revizie"]],
      ["gearbox_oil", ["ulei cutie"]],
      ["timing_belt", ["distributie"]],
      ["brake_fluid", ["lichid frana"]],
      ["coolant", ["antigel"]],
    ];
    for (const [maintenanceType, terms] of maintenanceTypes) {
      if (terms.some((term) => name.includes(term))) {
        const maintenanceField = this._canonicalEditableField(label, [
          ["last_km", ["ultimul schimb km"]],
          ["last_date", ["ultima data"]],
          ["interval_km", ["interval km"]],
          ["interval_days", ["interval zile"]],
          ["cost", ["cost estimat"]],
        ]);
        if (maintenanceField) return `${domain}:maintenance:${maintenanceType}:${maintenanceField}`;
      }
    }

    const consumableField = this._canonicalEditableField(label, [
      ["oil_amount", ["cantitate ulei"]],
      ["engine_oil", ["ulei motor"]],
      ["oil_filter", ["filtru ulei"]],
      ["air_filter", ["filtru aer"]],
      ["fuel_filter", ["filtru combustibil"]],
      ["cabin_filter", ["filtru habitaclu"]],
      ["gearbox_oil", ["ulei cutie"]],
      ["brake_fluid", ["lichid frana"]],
      ["coolant", ["lichid antigel"]],
      ["timing_kit", ["kit distributie"]],
["fuel_profile", ["motorizare"]],
      ["current_km", ["kilometri actuali"]],
    ]);
    if (consumableField) return `${domain}:field:${consumableField}`;

    return `${domain}:${name}`;
  }

  _canonicalEditableField(label, definitions) {
    for (const [key, terms] of definitions) {
      if (terms.some((term) => label.includes(term))) return key;
    }
    return "";
  }

  _editableEntityScore(entity) {
    const state = (entity.stateObj?.state ?? "").toString().trim().toLowerCase();
    let score = 0;
    if (state && state !== "unknown" && state !== "unavailable" && state !== "none") score += 100;
    if (state && state !== "0" && state !== "0.0") score += 10;
    if (!/_\d+$/.test(entity.entityId || "")) score += 1;
    return score;
  }

  _anyVehicleEditing() {
    return Boolean(this._editMode) || Boolean(this._editingVehicles?.size);
  }

  _isVehicleEditing(vehicle) {
    return Boolean(this._editMode) || this._editingVehicles?.has(vehicle.key);
  }

  _isEditableField(entity) {
    const name = this._normalize(this._friendly(entity));
    if (/zile ramase|km ramasi|status|valid|activ|expirat|ramase pana|ramasi pana/.test(name)) return false;
    return true;
  }

  _isVehicleEditField(entity) {
    return this._normalize(this._friendly(entity)).includes("kilometri actuali");
  }

  _isFuelProfileEditField(entity) {
    return this._normalize(this._friendly(entity)).includes("motorizare");
  }

  _isMaintenanceEditField(entity, terms) {
    const name = this._normalize(this._friendly(entity));
    const isTerm = terms.some((term) => name.includes(this._normalize(term)));
    const isMaintenanceInput = /ultimul schimb km|ultima data|interval km|interval zile|cost estimat/.test(name);
    return isTerm && isMaintenanceInput;
  }

  _isLegalEditField(entity, legalType) {
    const name = this._normalize(this._friendly(entity));
    if (!name.includes(legalType)) return false;
    if (legalType === "rca") {
      return /rca.*(incepe la|expira la|asigurator|numar polita|observatii|cost estimat)/.test(name);
    }
    if (legalType === "casco") {
      return /casco.*(incepe la|expira la|asigurator|numar polita|acoperire|observatii|cost estimat)/.test(name);
    }
    if (legalType === "itp") {
      return /itp.*(incepe la|expira la|statie|numar raport|observatii|cost estimat)/.test(name);
    }
    if (legalType === "rovinieta") {
      return /rovinieta.*(cost estimat)/.test(name);
    }
    return false;
  }

  _isConsumableEditField(entity) {
    const name = this._normalize(this._friendly(entity));
    if (/rca|casco|itp|rovinieta|revizie|distribu|ultimul schimb|ultima data|interval|cost estimat/.test(name)) return false;
    return this._isConsumableName(this._friendly(entity));
  }

  _editOrder(entity) {
    const name = this._normalize(this._friendly(entity));
    const order = [
      "kilometri actuali",
      "motorizare", "ultima data", "ultimul schimb km", "interval km", "interval zile", "cost estimat",
      "incepe la", "expira la", "asigurator", "numar polita", "acoperire", "statie", "numar raport", "observatii",
      "cantitate ulei", "ulei motor", "filtru ulei", "filtru aer", "filtru combustibil", "filtru habitaclu", "ulei cutie", "lichid frana", "lichid antigel", "kit distributie",
    ];
    const index = order.findIndex((item) => name.includes(item));
    return `${index === -1 ? 999 : index}`.padStart(3, "0") + name;
  }

  _renderField(entity) {
    const domain = entity.entityId.split(".")[0];
    const value = entity.stateObj.state === "unknown" || entity.stateObj.state === "unavailable" ? "" : entity.stateObj.state;
    const label = this._fieldLabel(this._friendly(entity));
    if (this._normalize(label).includes("motorizare")) {
      return `
        <label class="cmr-field">
          <span>${this._escape(label)}</span>
          <select data-entity="${entity.entityId}" data-domain="${domain}">${this._fuelProfileOptions(value || "diesel")}</select>
        </label>
      `;
    }
    const type = domain === "number" ? "number" : domain === "date" ? "date" : "text";
    return `
      <label class="cmr-field">
        <span>${this._escape(label)}</span>
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

    this.querySelector('[data-action="toggle-backup"]')?.addEventListener("click", () => {
      this._backupOpen = !this._backupOpen;
      this._backupMessage = "";
      this.render();
    });

    this.querySelectorAll('[data-action="set-tab"]').forEach((button) => {
      button.addEventListener("click", () => {
        const tab = button.dataset.tab || "vehicles";
        this._activeTab = ["costs", "fuel"].includes(tab) ? tab : "vehicles";
        this.render();
      });
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

    this.querySelectorAll('button[data-action="toggle-vehicle-edit"]').forEach((button) => {
      button.addEventListener("click", () => {
        const key = button.dataset.vehicle;
        if (!key) return;
        if (this._editingVehicles.has(key)) {
          this._editingVehicles.delete(key);
        } else {
          this._editingVehicles.add(key);
        }
        this.render();
      });
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

    this.querySelectorAll('button[data-action="toggle-service-form"]').forEach((button) => {
      button.addEventListener("click", () => {
        const key = button.dataset.vehicle;
        if (this._serviceFormOpen.has(key)) {
          this._serviceFormOpen.delete(key);
        } else {
          this._serviceFormOpen.add(key);
        }
        this.render();
      });
    });

    this.querySelectorAll('button[data-action="toggle-fuel-form"]').forEach((button) => {
      button.addEventListener("click", () => {
        const key = button.dataset.vehicle;
        if (!key) return;
        if (this._fuelFormOpen.has(key)) this._fuelFormOpen.delete(key); else this._fuelFormOpen.add(key);
        this.render();
      });
    });

    this.querySelectorAll('form[data-form="fuel-receipt"]').forEach((form) => {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        this._captureFuelReceiptDraft(form);
        this._inputEditing = false;
        this._addFuelReceipt(form);
      });
      form.addEventListener("input", () => this._captureFuelReceiptDraft(form));
      form.addEventListener("change", () => this._captureFuelReceiptDraft(form));
    });

    this.querySelectorAll('form[data-form="service-record"]').forEach((form) => {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        this._captureServiceRecordDraft(form);
        this._inputEditing = false;
        this._addServiceRecord(form);
      });
      form.addEventListener("input", () => this._captureServiceRecordDraft(form));
      form.addEventListener("change", () => this._captureServiceRecordDraft(form));
    });

    this.querySelectorAll('button[data-action="restore-service-record"]').forEach((button) => {
      button.addEventListener("click", () => this._restoreServiceRecord(button.dataset.recordId, button.dataset.vehicle));
    });

    this.querySelectorAll('button[data-action="delete-service-record"]').forEach((button) => {
      button.addEventListener("click", () => this._deleteServiceRecord(button.dataset.recordId, button.dataset.vehicle, {
        updatesMaintenance: button.dataset.updatesMaintenance === "1",
        restored: button.dataset.restored === "1",
      }));
    });

    this.querySelectorAll('button[data-action="toggle-edit-service-record"]').forEach((button) => {
      button.addEventListener("click", () => {
        const recordId = button.dataset.recordId;
        if (!recordId) return;
        if (this._serviceRecordEditOpen.has(recordId)) {
          this._serviceRecordEditOpen.delete(recordId);
        } else {
          this._serviceRecordEditOpen.add(recordId);
        }
        this.render();
      });
    });

    this.querySelectorAll('button[data-action="cancel-edit-service-record"]').forEach((button) => {
      button.addEventListener("click", () => {
        const recordId = button.dataset.recordId;
        if (!recordId) return;
        this._serviceRecordEditOpen.delete(recordId);
        delete this._serviceRecordEditDrafts[recordId];
        this.render();
      });
    });

    this.querySelectorAll('form[data-form="service-record-edit"]').forEach((form) => {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        this._captureServiceRecordEditDraft(form);
        this._inputEditing = false;
        this._updateServiceRecord(form);
      });
      form.addEventListener("input", () => this._captureServiceRecordEditDraft(form));
      form.addEventListener("change", () => this._captureServiceRecordEditDraft(form));
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

    this.querySelectorAll('button[data-action="ignore-casco"]').forEach((button) => {
      button.addEventListener("click", () => this._setCascoIgnored(button.dataset.vehicleId, true));
    });

    this.querySelectorAll('button[data-action="reactivate-casco"]').forEach((button) => {
      button.addEventListener("click", () => this._setCascoIgnored(button.dataset.vehicleId, false));
    });

    this.querySelector('[data-backup-filename]')?.addEventListener("input", (event) => {
      this._backupFilename = event.currentTarget.value || "car_manager_romania_backup.json";
    });
    this.querySelector('[data-action="backup-export"]')?.addEventListener("click", () => this._runBackupAction("export"));
    this.querySelector('[data-action="backup-validate"]')?.addEventListener("click", () => this._runBackupAction("validate"));
    this.querySelector('[data-action="backup-import-dry"]')?.addEventListener("click", () => this._runBackupAction("dry"));
    this.querySelector('[data-action="backup-import-real"]')?.addEventListener("click", () => this._runBackupAction("import"));

    this.querySelectorAll("input, textarea, select").forEach((input) => {
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

    this.querySelectorAll("input[data-entity], select[data-entity]").forEach((input) => {
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

  _captureServiceRecordDraft(form) {
    if (!form) return;
    const vehicleKey = form.dataset.vehicle;
    const data = new FormData(form);
    this._serviceRecordDrafts[vehicleKey] = {
      record_type: (data.get("record_type") || "service").toString(),
      date: (data.get("date") || "").toString(),
      km: (data.get("km") || "0").toString(),
      title: (data.get("title") || "").toString(),
      service_name: (data.get("service_name") || "").toString(),
      cost: (data.get("cost") || "0").toString(),
      invoice_number: (data.get("invoice_number") || "").toString(),
      notes: (data.get("notes") || "").toString(),
      update_maintenance: data.get("update_maintenance") === "on",
    };
  }

  _captureServiceRecordEditDraft(form) {
    if (!form) return;
    const recordId = form.dataset.recordId;
    if (!recordId) return;
    const data = new FormData(form);
    this._serviceRecordEditDrafts[recordId] = {
      title: (data.get("title") || "").toString(),
      service_name: (data.get("service_name") || "").toString(),
      cost: (data.get("cost") || "0").toString(),
      invoice_number: (data.get("invoice_number") || "").toString(),
      notes: (data.get("notes") || "").toString(),
    };
  }


  _captureFuelReceiptDraft(form) {
    if (!form) return;
    const vehicleKey = form.dataset.vehicle;
    const data = new FormData(form);
    this._fuelReceiptDrafts[vehicleKey] = {
      date: (data.get("date") || "").toString(),
      km: (data.get("km") || "").toString(),
      fuel_type: (data.get("fuel_type") || "").toString(),
      quantity: (data.get("quantity") || "").toString(),
      total_cost: (data.get("total_cost") || "").toString(),
      full_tank: data.get("full_tank") === "on",
      station: (data.get("station") || "").toString(),
      notes: (data.get("notes") || "").toString(),
    };
  }

  async _addFuelReceipt(form) {
    if (!this._hass || !form) return;
    const vehicleKey = form.dataset.vehicle;
    if (this._fuelReceiptBusy) return;
    const data = new FormData(form);
    const payload = {
      vehicle_id: form.dataset.vehicleRef || vehicleKey,
      date: (data.get("date") || "").toString(),
      km: Math.round(Number(data.get("km") || 0)),
      fuel_type: (data.get("fuel_type") || "").toString(),
      quantity: Number(data.get("quantity") || 0),
      total_cost: Number(data.get("total_cost") || 0),
      full_tank: data.get("full_tank") === "on",
      station: (data.get("station") || "").toString().trim(),
      notes: (data.get("notes") || "").toString().trim(),
    };
    this._fuelReceiptBusy = vehicleKey;
    this._fuelReceiptMessage[vehicleKey] = "";
    this.render();
    try {
      await this._hass.callService("car_manager_romania", "add_fuel_receipt", payload);
      this._fuelReceiptMessage[vehicleKey] = "Bonul a fost salvat. Integrarea se reîncarcă pentru actualizare.";
      this._fuelReceiptDrafts[vehicleKey] = {};
      this._fuelFormOpen.delete(vehicleKey);
    } catch (error) {
      this._fuelReceiptMessage[vehicleKey] = error?.message || "Nu am putut salva bonul.";
    } finally {
      this._fuelReceiptBusy = null;
      this.render();
    }
  }

  async _runBackupAction(action) {
    if (!this._hass || this._backupBusy) return;

    const filename = (this._backupFilename || "car_manager_romania_backup.json").trim() || "car_manager_romania_backup.json";
    if (filename.includes("/") || filename.includes("\\")) {
      this._backupMessage = "Numele fișierului nu trebuie să conțină cale sau directoare.";
      this.render();
      return;
    }

    if (action === "import") {
      const confirmed = window.confirm(
        "Importul merge va adăuga sau actualiza datele din backup. Nu șterge date existente, dar poate suprascrie valori pentru autovehicule/intervenții cu același ID. Continui?"
      );
      if (!confirmed) return;
    }

    const serviceMap = {
      export: "export_data",
      validate: "validate_backup",
      dry: "import_data",
      import: "import_data",
    };
    const service = serviceMap[action];
    if (!service) return;

    const payload = { filename };
    if (action === "dry" || action === "import") {
      payload.mode = "merge";
      payload.dry_run = action === "dry";
    }

    this._backupBusy = action;
    this._backupMessage = "";
    this.render();

    try {
      await this._hass.callService("car_manager_romania", service, payload);
      if (action === "export") {
        this._backupMessage = `Backup exportat în /config/${filename}. Descarcă-l local din File editor / Studio Code și păstrează-l în siguranță.`;
      } else if (action === "validate") {
        this._backupMessage = "Validarea a fost pornită. Rezultatul apare în notificările Home Assistant.";
      } else if (action === "dry") {
        this._backupMessage = "Simularea importului a fost pornită. Rezultatul apare în notificările Home Assistant.";
      } else {
        this._backupMessage = "Importul merge a fost pornit. Integrarea se va reîncărca dacă datele au fost aplicate.";
      }
    } catch (error) {
      this._backupMessage = error?.message || "Operațiunea de backup/restore a eșuat.";
    } finally {
      this._backupBusy = null;
      this.render();
    }
  }

  async _addServiceRecord(form) {
    if (!this._hass || !form) return;

    const vehicleKey = form.dataset.vehicle;
    if (this._serviceRecordBusy) return;

    const data = new FormData(form);
    const payload = {
      vehicle_id: form.dataset.vehicleRef || vehicleKey,
      record_type: (data.get("record_type") || "custom").toString(),
      date: (data.get("date") || "").toString(),
      km: Math.round(Number(data.get("km") || 0)),
      title: (data.get("title") || "").toString().trim(),
      service_name: (data.get("service_name") || "").toString().trim(),
      cost: Number(data.get("cost") || 0),
      invoice_number: (data.get("invoice_number") || "").toString().trim(),
      notes: (data.get("notes") || "").toString().trim(),
      update_maintenance: data.get("update_maintenance") === "on",
    };

    if (!payload.title) payload.title = this._recordTypeLabel(payload.record_type);
    if (!Number.isFinite(payload.km) || payload.km < 0) payload.km = 0;
    if (!Number.isFinite(payload.cost) || payload.cost < 0) payload.cost = 0;

    this._serviceRecordBusy = vehicleKey;
    this._serviceRecordMessage[vehicleKey] = "";
    this.render();

    try {
      await this._hass.callService("car_manager_romania", "add_service_record", payload);
      this._serviceRecordMessage[vehicleKey] = "Intervenția a fost salvată. Integrarea se reîncarcă pentru actualizare.";
      this._serviceRecordDrafts[vehicleKey] = {};
      this._serviceFormOpen.delete(vehicleKey);
    } catch (error) {
      this._serviceRecordMessage[vehicleKey] = error?.message || "Nu am putut salva intervenția.";
    } finally {
      this._serviceRecordBusy = null;
      this.render();
    }
  }

  async _restoreServiceRecord(recordId, vehicleKey) {
    if (!this._hass || !recordId || this._serviceRecordBusy) return;

    const confirmed = window.confirm("Revii la valorile anterioare acestei intervenții? Intervenția rămâne în istoric, dar va fi marcată ca restaurată.");
    if (!confirmed) return;

    this._serviceRecordBusy = vehicleKey || recordId;
    if (vehicleKey) this._serviceRecordMessage[vehicleKey] = "";
    this.render();

    try {
      await this._hass.callService("car_manager_romania", "restore_service_record", { record_id: recordId });
      if (vehicleKey) this._serviceRecordMessage[vehicleKey] = "Restore efectuat. Integrarea se reîncarcă.";
    } catch (error) {
      if (vehicleKey) this._serviceRecordMessage[vehicleKey] = error?.message || "Nu am putut face restore.";
    } finally {
      this._serviceRecordBusy = null;
      this.render();
    }
  }

  async _updateServiceRecord(form) {
    if (!this._hass || !form) return;

    const recordId = form.dataset.recordId;
    const vehicleKey = form.dataset.vehicle;
    if (!recordId || this._serviceRecordBusy) return;

    const data = new FormData(form);
    const payload = {
      record_id: recordId,
      title: (data.get("title") || "").toString().trim(),
      service_name: (data.get("service_name") || "").toString().trim(),
      cost: Number(data.get("cost") || 0),
      invoice_number: (data.get("invoice_number") || "").toString().trim(),
      notes: (data.get("notes") || "").toString().trim(),
    };

    if (!Number.isFinite(payload.cost) || payload.cost < 0) payload.cost = 0;

    this._serviceRecordBusy = recordId;
    if (vehicleKey) this._serviceRecordMessage[vehicleKey] = "";
    this.render();

    try {
      await this._hass.callService("car_manager_romania", "update_service_record", payload);
      delete this._serviceRecordEditDrafts[recordId];
      this._serviceRecordEditOpen.delete(recordId);
      if (vehicleKey) this._serviceRecordMessage[vehicleKey] = "Intervenția a fost actualizată. Integrarea se reîncarcă.";
    } catch (error) {
      if (vehicleKey) this._serviceRecordMessage[vehicleKey] = error?.message || "Nu am putut actualiza intervenția.";
    } finally {
      this._serviceRecordBusy = null;
      this.render();
    }
  }

  async _deleteServiceRecord(recordId, vehicleKey, options = {}) {
    if (!this._hass || !recordId || this._serviceRecordBusy) return;

    const warning = options.updatesMaintenance && !options.restored
      ? "Această intervenție pare aplicată în mentenanță. Ștergerea elimină doar rândul din istoric, nu revine la valorile anterioare. Pentru revenire, folosește mai întâi Restore, apoi Șterge. Continui?"
      : "Ștergi această intervenție din istoric? Valorile de mentenanță ale autovehiculului nu se modifică.";
    const confirmed = window.confirm(warning);
    if (!confirmed) return;

    this._serviceRecordBusy = vehicleKey || recordId;
    if (vehicleKey) this._serviceRecordMessage[vehicleKey] = "";
    this.render();

    try {
      await this._hass.callService("car_manager_romania", "delete_service_record", { record_id: recordId });
      if (vehicleKey) this._serviceRecordMessage[vehicleKey] = "Intervenția a fost ștearsă din istoric. Integrarea se reîncarcă.";
    } catch (error) {
      if (vehicleKey) this._serviceRecordMessage[vehicleKey] = error?.message || "Nu am putut șterge intervenția.";
    } finally {
      this._serviceRecordBusy = null;
      this.render();
    }
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


  async _setCascoIgnored(vehicleId, ignored) {
    if (!this._hass || !vehicleId) return;

    const confirmed = window.confirm(ignored
      ? "Ascunzi CASCO pentru acest autovehicul?"
      : "Reactivezi CASCO pentru acest autovehicul?");
    if (!confirmed) return;

    try {
      await this._hass.callService("car_manager_romania", "set_legal_option", {
        vehicle_id: vehicleId,
        legal_type: "casco",
        ignored,
      });
    } catch (error) {
      window.alert(error?.message || (ignored ? "Nu am putut ascunde CASCO pentru acest autovehicul." : "Nu am putut reactiva CASCO pentru acest autovehicul."));
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
    const cascoStatus = this._findSensorByName(vehicle, ["casco", "status"]);
    const cascoDays = this._findSensorByName(vehicle, ["casco", "zile", "ramase"]);
    const cascoExpiry = this._findByName(vehicle, ["casco", "expir"]);
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
      cascoStatus: this._entityValue(cascoStatus),
      cascoDays: this._formatDays(this._entityValue(cascoDays)),
      cascoExpiry: this._entityValue(cascoExpiry),
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
      /cost estimat/i,
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
    return label.replace(/\s+(Kilometri|Status|RCA|CASCO|ITP|Rovinietă|Revizie|Ulei|Distribuție|Lichid).*$/i, "").trim();
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
      "_rca_status", "_rca_days_remaining", "_casco_status", "_casco_days_remaining", "_itp_status", "_itp_days_remaining",
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
      "_kilometri", "_km", "_status", "_rca_status", "_casco_status", "_itp_status", "_rovinieta_status",
      "_rca_expiry", "_casco_expiry", "_itp_expiry", "_rovinieta_expiry", "_revizie_generala_status",
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

  _shouldShowCascoTile(summary) {
    return this._normalize(summary?.cascoStatus || "") !== "neconfigurat";
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
      .cmr-tabs { display: flex; gap: 8px; margin-top: 14px; padding: 4px; border-radius: 999px; background: color-mix(in srgb, var(--card-background-color) 88%, var(--primary-color) 12%); border: 1px solid var(--divider-color); }
      .cmr-tab { flex: 1 1 0; border: 0; border-radius: 999px; padding: 8px 10px; color: var(--secondary-text-color); background: transparent; cursor: pointer; font-weight: 900; }
      .cmr-tab.is-active { color: var(--primary-text-color); background: color-mix(in srgb, var(--primary-color) 22%, transparent); }
      .cmr-title { font-size: 20px; font-weight: 800; letter-spacing: -0.02em; }
      .cmr-subtitle, .cmr-plate, .cmr-row-muted, .cmr-tile-sub { color: var(--secondary-text-color); font-size: 12px; }
      .cmr-mode, .cmr-action { border: 0; border-radius: 999px; padding: 8px 12px; color: var(--primary-text-color); background: color-mix(in srgb, var(--primary-color) 14%, transparent); cursor: pointer; font-weight: 700; }
      .cmr-mode[disabled], .cmr-action[disabled] { opacity: .6; cursor: wait; }
      .cmr-secondary { background: color-mix(in srgb, var(--secondary-text-color) 12%, transparent); }
      .cmr-backup-panel { margin-top: 14px; padding: 14px; border-radius: 18px; background: color-mix(in srgb, var(--card-background-color) 86%, var(--primary-color) 14%); border: 1px solid var(--divider-color); }
      .cmr-backup-text, .cmr-backup-note { color: var(--secondary-text-color); font-size: 12px; line-height: 1.35; margin-top: 6px; }
      .cmr-backup-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
      .cmr-backup-field { margin-top: 10px; }
      .cmr-vehicle { margin-top: 16px; padding: 14px; border-radius: 18px; background: color-mix(in srgb, var(--card-background-color) 86%, var(--primary-color) 14%); border: 1px solid var(--divider-color); }
      .cmr-vehicle-title { font-size: 17px; font-weight: 800; }
      .cmr-km { white-space: nowrap; font-weight: 800; font-size: 18px; }
      .cmr-overall { margin-top: 14px; padding: 11px 12px; border-radius: 16px; background: var(--card-background-color); border: 1px solid var(--divider-color); border-left: 5px solid var(--cmr-accent, var(--divider-color)); }
      .cmr-overall-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
      .cmr-overall-title { font-size: 13px; font-weight: 900; }
      .cmr-overall-badge { flex: 0 0 auto; border-radius: 999px; padding: 5px 9px; font-size: 11px; font-weight: 900; background: color-mix(in srgb, var(--cmr-accent, var(--secondary-text-color)) 18%, transparent); color: var(--primary-text-color); }
      .cmr-overall-list { display: flex; flex-direction: column; gap: 5px; margin-top: 8px; }
      .cmr-overall-item { display: flex; align-items: baseline; gap: 6px; min-width: 0; color: var(--secondary-text-color); font-size: 12px; line-height: 1.3; }
      .cmr-overall-item strong { color: var(--primary-text-color); overflow-wrap: anywhere; }
      .cmr-overall-action { margin-left: auto; flex: 0 0 auto; }
      .cmr-overall-dot { width: 7px; height: 7px; border-radius: 999px; background: var(--cmr-accent, var(--secondary-text-color)); flex: 0 0 auto; }
      .cmr-overall-ok { color: var(--secondary-text-color); font-size: 12px; line-height: 1.35; }
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
      .cmr-section-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; border-bottom: 1px solid var(--divider-color); margin-bottom: 8px; }
      .cmr-section-head .cmr-section-title { border-bottom: 0; margin-bottom: 0; }
      .cmr-mini-action { border: 0; border-radius: 999px; padding: 5px 9px; color: var(--primary-text-color); background: color-mix(in srgb, var(--primary-color) 14%, transparent); cursor: pointer; font-size: 11px; font-weight: 800; white-space: nowrap; }
      .cmr-service-form { background: color-mix(in srgb, var(--card-background-color) 70%, transparent); border-radius: 14px; padding: 10px; margin: 8px 0 10px; }
      .cmr-history-edit-form { margin-top: 8px; border: 1px solid color-mix(in srgb, var(--divider-color) 75%, transparent); }
      .cmr-service-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 10px; }
      .cmr-service-wide { grid-column: 1 / -1; }
      .cmr-field textarea, .cmr-field select { box-sizing: border-box; width: 100%; min-width: 0; border-radius: 10px; border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); padding: 8px 10px; font: inherit; }
      .cmr-check { display: flex; gap: 8px; align-items: flex-start; margin: 10px 0 4px; color: var(--secondary-text-color); font-size: 12px; line-height: 1.35; }
      .cmr-history-list { display: flex; flex-direction: column; gap: 8px; }
      .cmr-history-row { display: flex; justify-content: space-between; gap: 8px; padding: 8px 0; border-top: 1px solid color-mix(in srgb, var(--divider-color) 70%, transparent); }
      .cmr-history-row:first-child { border-top: 0; }
      .cmr-history-main { min-width: 0; }
      .cmr-history-title { font-weight: 800; font-size: 13px; }
      .cmr-history-notes { color: var(--secondary-text-color); font-size: 12px; margin-top: 3px; white-space: pre-wrap; }
      .cmr-history-empty { color: var(--secondary-text-color); font-size: 12px; padding: 6px 0; }
      .cmr-history-actions { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; flex: 0 0 auto; }
      .cmr-history-row-restored { opacity: .78; }
      .cmr-history-badge { display: inline-block; margin-left: 5px; padding: 2px 6px; border-radius: 999px; color: var(--primary-text-color); font-size: 10px; }
      .cmr-history-badge-active { background: color-mix(in srgb, var(--success-color, #2e9d58) 22%, transparent); }
      .cmr-history-badge-restored { background: color-mix(in srgb, var(--warning-color) 20%, transparent); }
      .cmr-history-badge-info { background: color-mix(in srgb, var(--secondary-text-color) 16%, transparent); }
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
      .cmr-costs-panel { margin-top: 16px; padding: 14px; border-radius: 18px; background: color-mix(in srgb, var(--card-background-color) 86%, var(--primary-color) 14%); border: 1px solid var(--divider-color); }
      .cmr-cost-summary-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-top: 10px; }
      .cmr-check { display: flex; align-items: center; gap: 8px; margin: 8px 0; font-size: 13px; font-weight: 800; }
      .cmr-cost-card { padding: 12px; border-radius: 16px; background: var(--card-background-color); border: 1px solid var(--divider-color); }
      .cmr-cost-title { color: var(--secondary-text-color); font-size: 12px; font-weight: 900; }
      .cmr-cost-value { margin-top: 6px; font-size: 20px; font-weight: 950; letter-spacing: -0.02em; }
      .cmr-cost-section { margin-top: 14px; padding: 12px; border-radius: 16px; background: color-mix(in srgb, var(--card-background-color) 92%, var(--primary-color) 8%); }
      .cmr-cost-table { display: flex; flex-direction: column; gap: 0; }
      .cmr-cost-table-row { display: grid; grid-template-columns: minmax(0, 1.35fr) repeat(3, minmax(72px, .55fr)); gap: 8px; align-items: center; padding: 9px 0; border-top: 1px solid color-mix(in srgb, var(--divider-color) 70%, transparent); }
      .cmr-cost-table-row:first-child { border-top: 0; }
      .cmr-cost-table-row span { min-width: 0; overflow-wrap: anywhere; }
      .cmr-cost-table-row small { display: block; color: var(--secondary-text-color); font-size: 11px; margin-top: 2px; }
      .cmr-cost-table-head { color: var(--secondary-text-color); font-size: 11px; font-weight: 900; text-transform: uppercase; letter-spacing: .03em; }
      .cmr-cost-chips { display: flex; flex-wrap: wrap; gap: 8px; }
      .cmr-cost-chip { display: flex; gap: 8px; align-items: center; padding: 8px 10px; border-radius: 999px; background: var(--card-background-color); border: 1px solid var(--divider-color); }
      .cmr-cost-chip span { color: var(--secondary-text-color); font-size: 12px; font-weight: 800; }
      .cmr-cost-chip strong { font-size: 12px; }
      .cmr-cost-list { display: flex; flex-direction: column; gap: 8px; }
      .cmr-cost-item { display: flex; justify-content: space-between; gap: 10px; align-items: center; padding: 10px; border-radius: 14px; background: var(--card-background-color); border: 1px solid var(--divider-color); }
      .cmr-cost-item-main { min-width: 0; }
      .cmr-cost-item-title { font-weight: 900; overflow-wrap: anywhere; }
      .cmr-cost-item-title span { margin-left: 5px; color: var(--secondary-text-color); font-size: 12px; font-weight: 700; }
      .cmr-cost-item-value { flex: 0 0 auto; font-weight: 950; }
      .cmr-field { display: grid; grid-template-columns: minmax(105px, 1fr) minmax(120px, 260px); align-items: center; gap: 10px; padding: 7px 0; border-top: 1px solid color-mix(in srgb, var(--divider-color) 70%, transparent); font-weight: 700; }
      .cmr-field span { line-height: 1.25; }
      .cmr-field:first-of-type { border-top: 0; }
      .cmr-field input { width: 100%; min-width: 0; box-sizing: border-box; border: 1px solid var(--divider-color); border-radius: 10px; padding: 8px 10px; background: var(--card-background-color); color: var(--primary-text-color); }
      .cmr-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
      .cmr-empty { margin-top: 14px; color: var(--secondary-text-color); padding: 14px; border: 1px dashed var(--divider-color); border-radius: 14px; }
      @container (max-width: 420px) {
        .cmr-header, .cmr-vehicle-head { align-items: flex-start; }
        .cmr-header-actions { width: 100%; justify-content: flex-start; }
        .cmr-add-grid, .cmr-cost-summary-grid { grid-template-columns: 1fr; }
        .cmr-field { grid-template-columns: 1fr; }
        .cmr-service-grid { grid-template-columns: 1fr; }
        .cmr-history-row { flex-direction: column; }
      }
      @media (max-width: 760px) {
        .cmr-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 6px; }
        .cmr-tile { padding: 8px 5px; min-height: 84px; }
        .cmr-tile-main { font-size: 16px; }
        .cmr-tile-sub { font-size: 11px; }
        .cmr-tile-top { font-size: 9.5px; }
        .cmr-row, .cmr-cost-table-row { grid-template-columns: 1fr; }
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
