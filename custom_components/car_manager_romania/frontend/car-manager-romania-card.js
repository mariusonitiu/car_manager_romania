class CarManagerRomaniaCard extends HTMLElement {
  static get version() { return "1.0.60"; }
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
    this._fuelReceiptEditOpen = this._fuelReceiptEditOpen || new Set();
    this._fuelReceiptEditDrafts = this._fuelReceiptEditDrafts || {};
    this._fuelReceiptBusy = this._fuelReceiptBusy || null;
    this._fuelReceiptMessage = this._fuelReceiptMessage || {};
    this._fuelVehicleFilter = this._fuelVehicleFilter || "all";
    this._tireVehicleFilter = this._tireVehicleFilter || "all";
    this._tireFormOpen = this._tireFormOpen || new Set();
    this._tireSetDrafts = this._tireSetDrafts || {};
    this._tireSetEditOpen = this._tireSetEditOpen || new Set();
    this._tireSetEditDrafts = this._tireSetEditDrafts || {};
    this._tireSetBusy = this._tireSetBusy || null;
    this._tireSetMessage = this._tireSetMessage || {};
    this._equipmentVehicleFilter = this._equipmentVehicleFilter || "all";
    this._batteryVehicleFilter = this._batteryVehicleFilter || "all";
    this._batteryFormOpen = this._batteryFormOpen || new Set();
    this._batteryDrafts = this._batteryDrafts || {};
    this._batteryEditOpen = this._batteryEditOpen || new Set();
    this._batteryEditDrafts = this._batteryEditDrafts || {};
    this._batteryBusy = this._batteryBusy || null;
    this._batteryMessage = this._batteryMessage || {};
    this._equipmentFormOpen = this._equipmentFormOpen || new Set();
    this._equipmentDrafts = this._equipmentDrafts || {};
    this._equipmentEditOpen = this._equipmentEditOpen || new Set();
    this._equipmentEditDrafts = this._equipmentEditDrafts || {};
    this._equipmentBusy = this._equipmentBusy || null;
    this._equipmentMessage = this._equipmentMessage || {};
    this._serviceRecordMessage = this._serviceRecordMessage || {};
    this._inputEditing = this._inputEditing || false;
    this._backupOpen = this._backupOpen || false;
    this._backupBusy = this._backupBusy || null;
    this._backupFilename = this._backupFilename || "car_manager_romania_backup.json";
    this._backupMessage = this._backupMessage || "";
    this._activeTab = this._activeTab || this.config.default_tab || "vehicles";
    this._tabHoverLabel = this._tabHoverLabel || "";
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
    const licenseAccess = this._splitVehiclesByLicense(vehicles, visibleVehicles);
    const activeVisibleVehicles = licenseAccess.active;
    const lockedVisibleVehicles = licenseAccess.locked;
    const inactiveVehicles = inactiveVehiclesAll.filter((vehicle) =>
      this._selectedVehicle ? this._matchesVehicle(vehicle, this._selectedVehicle) : true
    );
    const subtitle = this._vehicleSubtitle(activeVisibleVehicles.length, lockedVisibleVehicles.length);
    const premiumAccess = this._licenseAllowsPremiumFeatures();
    if (!premiumAccess && !["vehicles", "license"].includes(this._activeTab || "vehicles")) {
      this._activeTab = "vehicles";
    }

    this.innerHTML = `
      <ha-card>
        <style>${this._styles()}</style>
        <div class="cmr-card">
          <div class="cmr-header">
            <div class="cmr-header-main">
              <img
                class="cmr-brand-icon"
                src="/car_manager_romania_brand/icon.png"
                alt=""
                loading="lazy"
              >
              <div class="cmr-header-text">
                <div class="cmr-title">${this._escape(this.config.title || "Car Manager România")}</div>
                <div class="cmr-subtitle">${this._escape(subtitle)}</div>
              </div>
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
            ? this._renderCostsTab(activeVisibleVehicles)
            : this._activeTab === "fuel"
              ? this._renderFuelTab(activeVisibleVehicles)
              : this._activeTab === "tires"
                ? this._renderTiresTab(activeVisibleVehicles)
                : this._activeTab === "equipment"
                  ? this._renderEquipmentTab(activeVisibleVehicles)
                  : this._activeTab === "battery"
                    ? this._renderBatteryTab(activeVisibleVehicles)
                    : this._activeTab === "license"
                      ? this._renderLicenseTab()
                      : `${this._anyVehicleEditing() && inactiveVehicles.length ? this._renderInactiveVehicles(inactiveVehicles) : ""}${activeVisibleVehicles.length ? activeVisibleVehicles.map((vehicle) => this._renderVehicle(vehicle)).join("") : ""}${lockedVisibleVehicles.length ? lockedVisibleVehicles.map((item) => this._renderLicenseLockedVehicle(item.vehicle, item.index)).join("") : ""}${!activeVisibleVehicles.length && !lockedVisibleVehicles.length ? this._renderEmpty() : ""}`}
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

  _vehicleAccessKey(vehicle) {
    return (vehicle?.vehicle_id || vehicle?.key || vehicle?.label || "").toString();
  }

  _licenseAllowsAllVehicles() {
    return this._licenseAllowsPremiumFeatures();
  }

  _licenseAllowsPremiumFeatures() {
    const status = this._licenseEntityValue("status_licenta");
    const plan = this._licenseEntityValue("plan_licenta");
    return this._hasValidLicenseStatus(status) || this._isTrialLicenseStatus(status, plan);
  }

  _splitVehiclesByLicense(allVehicles, visibleVehicles) {
    if (this._licenseAllowsAllVehicles()) {
      return {
        active: visibleVehicles,
        locked: [],
      };
    }

    const active = [];
    const locked = [];
    const allIndexes = new Map();
    allVehicles.forEach((vehicle, index) => {
      const key = this._vehicleAccessKey(vehicle);
      if (key) allIndexes.set(key, index);
    });

    for (const vehicle of visibleVehicles) {
      const key = this._vehicleAccessKey(vehicle);
      if (this._isLicenseBlockedVehicle(vehicle)) {
        locked.push({ vehicle, index: (allIndexes.get(key) ?? 0) + 1 });
      } else {
        active.push(vehicle);
      }
    }

    return { active, locked };
  }

  _isLicenseBlockedVehicle(vehicle) {
    return Boolean(vehicle?.license_blocked || vehicle?.entities?.some(({ stateObj }) => (stateObj.attributes || {}).license_blocked));
  }

  _vehicleSubtitle(activeCount, lockedCount) {
    const activeText = `${activeCount || 0} autovehicul${activeCount === 1 ? "" : "e"} monitorizat${activeCount === 1 ? "" : "e"}`;
    if (!lockedCount) return activeText;
    return `${activeText} · ${lockedCount} dezactivat${lockedCount === 1 ? "" : "e"} fără licență`;
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
    group.license_blocked = Boolean(group.license_blocked)
      || group.entities.some(({ stateObj }) => (stateObj.attributes || {}).license_blocked)
      || this._shouldTreatUnavailableGroupAsLicenseLocked(group);
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


  _tabDefinitions() {
    const basicTabs = [
      ["vehicles", "Mașini", "mdi:car-multiple"],
      ["license", "Licență", "mdi:key-chain-variant"],
    ];

    if (!this._licenseAllowsPremiumFeatures()) {
      return basicTabs;
    }

    return [
      ["vehicles", "Mașini", "mdi:car-multiple"],
      ["costs", "Costuri", "mdi:cash-multiple"],
      ["fuel", "Combustibil", "mdi:gas-station"],
      ["tires", "Anvelope", "mdi:tire"],
      ["equipment", "Siguranță", "mdi:shield-car"],
      ["battery", "Baterie", "mdi:car-battery"],
      ["license", "Licență", "mdi:key-chain-variant"],
    ];
  }

  _tabActiveLabel() {
    const active = this._activeTab || "vehicles";
    return this._tabDefinitions().find(([key]) => key === active)?.[1] || "Mașini";
  }

  _isCompactPointerDevice() {
    try {
      return !!window.matchMedia && window.matchMedia("(hover: none), (pointer: coarse)").matches;
    } catch (_err) {
      return false;
    }
  }

  _tabDisplayLabel() {
    if (this._tabHoverLabel) return this._tabHoverLabel;
    return this._isCompactPointerDevice() ? this._tabActiveLabel() : "";
  }

  _renderLicenseTab() {
    const status = this._licenseEntityValue("status_licenta");
    const plan = this._licenseEntityValue("plan_licenta");
    const validUntil = this._licenseEntityValue("valabila_pana_la");
    const checkedAt = this._licenseEntityValue("ultima_verificare_licenta");
    const account = this._licenseEntityValue("cont_licenta");
    const maskedKey = this._licenseEntityValue("cod_licenta_mascat");
    const message = this._licenseEntityValue("mesaj_licenta");
    const textEntity = this._licenseEntity("text", "cod_licenta_noua");
    const buttonEntity = this._licenseEntity("button", "aplica_licenta");
    const currentInput = this._licenseDraft ?? this._licenseEntityValue("cod_licenta_noua", "text") ?? "TRIAL";
    const statusClass = this._licenseStatusClass(status);
    const hasValidLicense = this._hasValidLicenseStatus(status);
    const isTrialLicense = this._isTrialLicenseStatus(status, plan);
    const showDonationHint = !hasValidLicense || isTrialLicense;

    return `
      <section class="cmr-license-panel">
        <div class="cmr-section-head">
          <div>
            <div class="cmr-section-title">Licență integrare</div>
            <div class="cmr-section-subtitle">Activează integrarea cu o licență validă sau folosește perioada de test.</div>
          </div>
          <span class="cmr-license-badge ${statusClass}">${this._escape(status || "Neverificată")}</span>
        </div>

        <div class="cmr-license-grid">
          ${this._renderLicenseInfo("Plan", plan)}
          ${this._renderLicenseInfo("Valabilă până la", validUntil)}
          ${this._renderLicenseInfo("Ultima verificare", checkedAt)}
          ${this._renderLicenseInfo("Cont", account)}
          ${this._renderLicenseInfo("Cod", maskedKey)}
          ${this._renderLicenseInfo("Mesaj", message)}
        </div>

        ${showDonationHint ? `<div class="cmr-license-donation-note">Dacă nu ai încă o licență validă, aceasta se poate obține printr-o donație minimă pe Buy me a Coffee. Pentru emiterea licenței, după donație scrie în mesaj: „Licență Car Manager România” și adresa de e-mail pe care dorești să primești cheia.</div>` : ""}
        <a class="cmr-bmc-button" href="https://www.buymeacoffee.com/mariusonitiu" target="_blank" rel="noopener noreferrer" aria-label="Buy me a coffee">
          <span class="cmr-bmc-emoji">☕</span>
          <span>Buy me a coffee</span>
        </a>

        <form class="cmr-license-form" data-form="license">
          <label>
            <span>Cod licență</span>
            <input type="text" name="license_key" autocomplete="off" spellcheck="false" value="${this._escape(currentInput)}" ${textEntity ? "" : "disabled"}>
          </label>
          <div class="cmr-license-actions">
            <button class="cmr-action" type="submit" ${textEntity && buttonEntity ? "" : "disabled"}>Aplică licența</button>
            <button class="cmr-action cmr-secondary" type="button" data-action="license-refresh">Actualizează status</button>
          </div>
          <div class="cmr-backup-note">Pentru trial poți lăsa valoarea <strong>TRIAL</strong>. După aplicare, cheia rămâne salvată local și în card este afișată doar mascat.</div>
          ${!textEntity || !buttonEntity ? `<div class="cmr-message is-warn">Entitățile de licențiere nu sunt încă disponibile. Dacă este prima instalare, verifică dacă integrarea este adăugată în Devices & services, apoi fă refresh la card.</div>` : ""}
          ${this._licenseMessage ? `<div class="cmr-message">${this._escape(this._licenseMessage)}</div>` : ""}
        </form>
      </section>
    `;
  }

  _renderLicenseInfo(label, value) {
    const safeValue = value && value !== "-" ? value : "—";
    return `
      <div class="cmr-license-info">
        <div class="cmr-license-label">${this._escape(label)}</div>
        <div class="cmr-license-value">${this._escape(safeValue)}</div>
      </div>
    `;
  }

  _licenseEntity(domain, objectId) {
    const states = this._hass?.states || {};

    // Home Assistant poate genera entity_id-uri diferite în funcție de numele
    // hub-ului/config entry-ului. La unele instalări entitățile sunt create cu
    // prefixul car_manager_romania_, iar la altele cu prefixul car_manager_.
    // Cardul trebuie să accepte ambele variante, fără redenumiri manuale.
    const prefixes = ["car_manager_romania", "car_manager"];
    const objectAliases = {
      cod_licenta_noua: ["cod_licenta_noua", "cod_licenta_nou"],
      cod_licenta_nou: ["cod_licenta_nou", "cod_licenta_noua"],
    };
    const wantedObjectIds = objectAliases[objectId] || [objectId];

    for (const prefix of prefixes) {
      for (const wantedObjectId of wantedObjectIds) {
        const exactEntityId = `${domain}.${prefix}_${wantedObjectId}`;
        if (states[exactEntityId]) return states[exactEntityId];
      }
    }

    const entries = Object.entries(states).filter(([entityId]) => {
      if (!entityId.startsWith(`${domain}.`)) return false;
      const objectPart = entityId.split(".")[1] || "";
      if (objectPart.startsWith("utilitati_romania_")) return false;
      return prefixes.some((prefix) => objectPart === prefix || objectPart.startsWith(`${prefix}_`));
    });

    // Nu rezolvăm după sufix generic. Acceptăm doar entități care aparțin clar
    // de Car Manager, inclusiv variante păstrate de HA cu _2, _3.
    const byObjectId = entries.find(([entityId]) => {
      const objectPart = entityId.split(".")[1] || "";
      return prefixes.some((prefix) => wantedObjectIds.some((wantedObjectId) => {
        const expectedObjectId = `${prefix}_${wantedObjectId}`;
        if (objectPart === expectedObjectId) return true;
        if (!objectPart.startsWith(`${expectedObjectId}_`)) return false;
        const suffix = objectPart.slice(expectedObjectId.length + 1);
        return /^\d+$/.test(suffix);
      }));
    });
    if (byObjectId) return byObjectId[1];

    const normalizedWanted = this._normalize(objectId);
    const aliases = {
      cod_licenta_noua: ["cod licenta nou", "cod licenta noua", "license key", "licenta nou"],
      cod_licenta_nou: ["cod licenta nou", "cod licenta noua", "license key", "licenta nou"],
      aplica_licenta: ["aplica licenta", "aplicare licenta", "apply license"],
      actualizeaza_status_licenta: ["actualizeaza status licenta", "actualizare status licenta", "refresh license", "revalidate license"],
      status_licenta: ["status licenta"],
      plan_licenta: ["plan licenta"],
      valabila_pana_la: ["valabila pana la", "valabil pana la"],
      ultima_verificare_licenta: ["ultima verificare licenta"],
      cont_licenta: ["cont licenta", "utilizator licenta"],
      cod_licenta_mascat: ["cod licenta mascat", "cheie licenta mascata"],
      mesaj_licenta: ["mesaj licenta"],
    };

    const allowedNames = [
      normalizedWanted,
      ...wantedObjectIds.map((value) => this._normalize(value)),
      ...(aliases[objectId] || []),
    ].map((value) => this._normalize(value));

    const byFriendlyName = entries.find(([, stateObj]) => {
      const friendlyName = this._normalize(stateObj?.attributes?.friendly_name || "");
      return allowedNames.some((name) => friendlyName === name || friendlyName.endsWith(` ${name}`));
    });
    if (byFriendlyName) return byFriendlyName[1];

    const bySafeObjectPart = entries.find(([entityId]) => {
      let objectPart = entityId.split(".")[1] || "";
      for (const prefix of prefixes) {
        if (objectPart.startsWith(`${prefix}_`)) {
          objectPart = objectPart.slice(prefix.length + 1);
          break;
        }
      }
      objectPart = this._normalize(objectPart);
      return allowedNames.some((name) => {
        const slug = name.replaceAll(" ", "_");
        return objectPart === slug || objectPart.includes(slug);
      });
    });
    if (bySafeObjectPart) return bySafeObjectPart[1];

    return null;
  }


  _licenseRefreshButtonEntity() {
    const direct = this._licenseEntity("button", "actualizeaza_status_licenta");
    if (direct?.entity_id) return direct;

    const states = this._hass?.states || {};
    const entries = Object.entries(states).filter(([entityId]) => {
      if (!entityId.startsWith("button.")) return false;
      const objectPart = entityId.split(".")[1] || "";
      return objectPart.startsWith("car_manager_romania_") || objectPart.startsWith("car_manager_");
    });

    const matchesRefresh = ([entityId, stateObj]) => {
      const objectPart = this._normalize(entityId.split(".")[1] || "");
      const friendlyName = this._normalize(stateObj?.attributes?.friendly_name || "");
      const haystack = `${objectPart} ${friendlyName}`;

      // Home Assistant can slightly alter Romanian slugs generated from names
      // with diacritics. Match only Car Manager buttons, but accept partial
      // forms such as "licen", "licenta", "licenta_2" etc.
      return (
        haystack.includes("actualizeaza") &&
        haystack.includes("status") &&
        haystack.includes("licen")
      ) || (
        haystack.includes("refresh") && haystack.includes("license")
      ) || (
        haystack.includes("revalidate") && haystack.includes("license")
      );
    };

    const found = entries.find(matchesRefresh);
    return found ? found[1] : null;
  }

  _licenseEntityValue(objectId, domain = "sensor") {
    const stateObj = this._licenseEntity(domain, objectId);
    const value = stateObj?.state;
    if (value === undefined || value === null || value === "" || value === "unknown" || value === "unavailable") return null;
    return value;
  }

  _hasValidLicenseStatus(status) {
    const normalized = this._normalize(status || "");
    return /activ|active|trial/.test(normalized) && !/inactiv|inactive|invalid|expir|revoc|produs|limita|eroare/.test(normalized);
  }

  _isTrialLicenseStatus(status, plan) {
    const normalizedStatus = this._normalize(status || "");
    const normalizedPlan = this._normalize(plan || "");
    return /trial|test/.test(normalizedStatus) || /trial|test/.test(normalizedPlan);
  }

  _licenseStatusClass(status) {
    const normalized = this._normalize(status || "");
    if (this._hasValidLicenseStatus(status)) return "is-good";
    if (/expir|invalid|revoc|produs|limita|inactiv|inactive/.test(normalized)) return "is-bad";
    if (/necunoscut|eroare|neverificat/.test(normalized)) return "is-warn";
    return "is-neutral";
  }

  _renderTabs() {
    const active = this._activeTab || "vehicles";
    const tabs = this._tabDefinitions();
    const label = this._tabDisplayLabel();
    return `
      <div class="cmr-tabs-wrap">
        <div class="cmr-tabs cmr-tabs-icon" role="tablist">
          ${tabs.map(([key, tabLabel, icon]) => `
            <button
              class="cmr-tab ${active === key ? "is-active" : ""}"
              data-action="set-tab"
              data-tab="${key}"
              data-label="${this._escape(tabLabel)}"
              type="button"
              title="${this._escape(tabLabel)}"
              aria-label="${this._escape(tabLabel)}"
            >
              <ha-icon icon="${icon}"></ha-icon>
            </button>
          `).join("")}
        </div>
        <div class="cmr-tab-current ${label ? "has-label" : ""}" aria-live="polite">${this._escape(label)}</div>
      </div>
    `;
  }

  _setTabHoverLabel(label) {
    if (!label || this._tabHoverLabel === label) return;
    this._tabHoverLabel = label;
    const labelElement = this.querySelector(".cmr-tab-current");
    if (labelElement) {
      labelElement.textContent = label;
      labelElement.classList.toggle("has-label", !!label);
    }
  }

  _clearTabHoverLabel() {
    const previous = this._tabHoverLabel;
    const nextLabel = this._isCompactPointerDevice() ? this._tabActiveLabel() : "";
    this._tabHoverLabel = "";
    if (!previous && !nextLabel) return;
    const labelElement = this.querySelector(".cmr-tab-current");
    if (labelElement) {
      labelElement.textContent = nextLabel;
      labelElement.classList.toggle("has-label", !!nextLabel);
    }
  }

  _renderCostsTab(vehicles) {
    if (!vehicles.length) return this._renderEmpty();

    const summaries = vehicles.map((vehicle) => this._costSummaryForVehicle(vehicle));
    const fuelSummaries = vehicles.map((vehicle) => this._fuelSummaryForVehicle(vehicle));
    const fuelByVehicle = new Map(fuelSummaries.map((summary) => [summary.key, summary]));
    const totalAnnualOperational = summaries.reduce((sum, item) => sum + item.annual, 0);
    const totalAnnualFuel = fuelSummaries.reduce((sum, item) => sum + item.yearCost, 0);
    const tireSummaries = vehicles.map((vehicle) => this._tireSummaryForVehicle(vehicle));
    const tireByVehicle = new Map(tireSummaries.map((summary) => [summary.key, summary]));
    const totalAnnualTires = tireSummaries.reduce((sum, item) => sum + item.yearCost, 0);
    const equipmentSummaries = vehicles.map((vehicle) => this._equipmentSummaryForVehicle(vehicle));
    const equipmentByVehicle = new Map(equipmentSummaries.map((summary) => [summary.key, summary]));
    const totalAnnualEquipment = equipmentSummaries.reduce((sum, item) => sum + item.yearCost, 0);
    const batterySummaries = vehicles.map((vehicle) => this._batterySummaryForVehicle(vehicle));
    const batteryByVehicle = new Map(batterySummaries.map((summary) => [summary.key, summary]));
    const totalAnnualBattery = batterySummaries.reduce((sum, item) => sum + item.yearCost, 0);
    const totalAnnual = totalAnnualOperational + totalAnnualFuel + totalAnnualTires + totalAnnualEquipment + totalAnnualBattery;
    const total30 = summaries.reduce((sum, item) => sum + item.upcoming30, 0);
    const total90 = summaries.reduce((sum, item) => sum + item.upcoming90, 0);
    const allUpcoming90 = summaries.flatMap((summary) => summary.items90.map((item) => ({ ...item, vehicle_label: summary.label })));
    const allUpcoming30 = allUpcoming90.filter((item) => this._toNumber(item.days_remaining) <= 30);
    const byType = this._groupCostItemsByType(allUpcoming90);
    const annualTypes = [
      { label: "Intervenții / termene", total: totalAnnualOperational },
      { label: "Combustibil", total: totalAnnualFuel },
      { label: "Anvelope", total: totalAnnualTires },
      { label: "Echipamente", total: totalAnnualEquipment },
      { label: "Baterie", total: totalAnnualBattery },
    ].filter((item) => item.total > 0);

    return `
      <section class="cmr-costs-panel">
        <div class="cmr-section-title">Costuri</div>
        <div class="cmr-cost-summary-grid">
          ${this._renderCostSummaryCard("Total anul curent", totalAnnual, "Intervenții, termene și combustibil")}
          ${this._renderCostSummaryCard("Intervenții / termene", totalAnnualOperational, "Din istoricul intervențiilor salvate")}
          ${this._renderCostSummaryCard("Combustibil anul curent", totalAnnualFuel, "Din bonurile salvate")}
          ${this._renderCostSummaryCard("Anvelope anul curent", totalAnnualTires, "Din seturile cumpărate")}
          ${this._renderCostSummaryCard("Echipamente anul curent", totalAnnualEquipment, "Trusă, stingător și dotări")}
          ${this._renderCostSummaryCard("Baterie anul curent", totalAnnualBattery, "După data montării")}
          ${this._renderCostSummaryCard("Următoarele 30 zile", total30, `${allUpcoming30.length} cheltuieli estimate`)}
          ${this._renderCostSummaryCard("Următoarele 90 zile", total90, `${allUpcoming90.length} cheltuieli estimate`)}
        </div>
        <div class="cmr-cost-section">
          <div class="cmr-section-title">Defalcare pe autovehicul</div>
          <div class="cmr-vehicle-cost-list">
            ${summaries.map((summary) => {
              const fuel = fuelByVehicle.get(summary.key)?.yearCost || 0;
              const tires = tireByVehicle.get(summary.key)?.yearCost || 0;
              const equipment = equipmentByVehicle.get(summary.key)?.yearCost || 0;
              const battery = batteryByVehicle.get(summary.key)?.yearCost || 0;
              return `
              <article class="cmr-vehicle-cost-card">
                <div class="cmr-vehicle-cost-head">
                  <div>
                    <strong>${this._escape(summary.label)}</strong>
                    ${summary.plate ? `<small>${this._escape(summary.plate)}</small>` : ""}
                  </div>
                  <div class="cmr-vehicle-cost-total">${this._formatMoney(summary.annual + fuel + tires + equipment + battery)}</div>
                </div>
                <div class="cmr-vehicle-cost-grid">
                  <div><span>Intervenții</span><strong>${this._formatMoney(summary.annual)}</strong></div>
                  <div><span>Combustibil</span><strong>${this._formatMoney(fuel)}</strong></div>
                  <div><span>Anvelope</span><strong>${this._formatMoney(tires)}</strong></div>
                  <div><span>Siguranță</span><strong>${this._formatMoney(equipment)}</strong></div>
                  <div><span>Baterie</span><strong>${this._formatMoney(battery)}</strong></div>
                  <div><span>30 zile</span><strong>${this._formatMoney(summary.upcoming30)}</strong></div>
                  <div><span>90 zile</span><strong>${this._formatMoney(summary.upcoming90)}</strong></div>
                </div>
              </article>`;
            }).join("")}
          </div>
        </div>
        <div class="cmr-cost-section">
          <div class="cmr-section-title">Defalcare pe tip, anul curent</div>
          ${annualTypes.length ? `
            <div class="cmr-cost-chips">
              ${annualTypes.map((item) => `<div class="cmr-cost-chip"><span>${this._escape(item.label)}</span><strong>${this._formatMoney(item.total)}</strong></div>`).join("")}
            </div>
          ` : `<div class="cmr-history-empty">Nu există costuri salvate pentru anul curent.</div>`}
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

    const allSummaries = vehicles.map((vehicle) => this._fuelSummaryForVehicle(vehicle));
    if (this._fuelVehicleFilter !== "all" && !allSummaries.some((summary) => summary.key === this._fuelVehicleFilter)) {
      this._fuelVehicleFilter = "all";
    }
    const summaries = this._fuelVehicleFilter === "all"
      ? allSummaries
      : allSummaries.filter((summary) => summary.key === this._fuelVehicleFilter);
    const totalYear = summaries.reduce((sum, item) => sum + item.yearCost, 0);
    const totalMonth = summaries.reduce((sum, item) => sum + item.monthCost, 0);
    const totalYearQuantity = summaries.reduce((sum, item) => sum + item.yearQuantity, 0);
    const totalMonthQuantity = summaries.reduce((sum, item) => sum + item.monthQuantity, 0);
    const totalYearCostForUnit = summaries.reduce((sum, item) => sum + item.yearUnitCostBase, 0);
    const averageUnitPrice = totalYearQuantity > 0 ? totalYearCostForUnit / totalYearQuantity : 0;
    const receipts = summaries.flatMap((summary) => summary.receipts.map((receipt) => ({ ...receipt, vehicle_label: summary.label })));
    const latestReceipt = this._latestFuelReceipt(receipts);

    return `
      <section class="cmr-costs-panel">
        <div class="cmr-section-head cmr-fuel-head">
          <div>
            <div class="cmr-section-title">Combustibil</div>
            <div class="cmr-row-muted">Rapoarte calculate din bonurile salvate</div>
          </div>
          <div class="cmr-fuel-head-actions">
            ${this._renderFuelVehicleFilter(allSummaries)}
            <button class="cmr-mini-action" type="button" data-action="export-fuel-history">Export combustibil</button>
          </div>
        </div>
        <div class="cmr-cost-summary-grid">
          ${this._renderCostSummaryCard("Combustibil anul curent", totalYear, "Din bonurile salvate")}
          ${this._renderCostSummaryCard("Combustibil luna curentă", totalMonth, "Din bonurile salvate")}
          ${this._renderCostSummaryCard("Cantitate anul curent", totalYearQuantity ? `${this._formatNumber(totalYearQuantity, 2)} L/kWh` : "—", totalMonthQuantity ? `Luna curentă: ${this._formatNumber(totalMonthQuantity, 2)} L/kWh` : "Fără alimentări luna curentă")}
          ${this._renderCostSummaryCard("Preț mediu", averageUnitPrice ? `${this._formatNumber(averageUnitPrice, 2)} RON/unitate` : "—", "Calculat din anul curent")}
          ${this._renderCostSummaryCard("Bonuri salvate", `${receipts.length}`, "Total alimentări afișate")}
          ${latestReceipt ? this._renderCostSummaryCard("Ultimul bon", this._formatMoney(latestReceipt.total_cost), `${this._formatDateForDisplay(latestReceipt.date || "")} · ${latestReceipt.vehicle_label || ""}`) : this._renderCostSummaryCard("Ultimul bon", "—", "Nu există bonuri salvate")}
        </div>
        ${summaries.map((summary) => this._renderFuelVehiclePanel(summary)).join("")}
      </section>
    `;
  }

  _renderFuelVehicleFilter(summaries) {
    if (!Array.isArray(summaries) || summaries.length <= 1) return "";
    return `
      <label class="cmr-fuel-filter">
        <span>Autovehicul</span>
        <select data-action="fuel-filter">
          <option value="all" ${this._fuelVehicleFilter === "all" ? "selected" : ""}>Toate</option>
          ${summaries.map((summary) => `<option value="${this._escape(summary.key)}" ${this._fuelVehicleFilter === summary.key ? "selected" : ""}>${this._escape(summary.label)}</option>`).join("")}
        </select>
      </label>
    `;
  }

  _fuelSummaryForVehicle(vehicle) {
    const attrs = this._vehicleStatusAttributes(vehicle);
    const yearSensor = this._findSensorByName(vehicle, ["combustibil", "anul", "curent"]);
    const monthSensor = this._findSensorByName(vehicle, ["combustibil", "luna", "curenta"]);
    const consumptionSensor = this._findSensorByName(vehicle, ["consum", "mediu", "combustibil"]);
    const receipts = Array.isArray(attrs.fuel_receipts) ? attrs.fuel_receipts : [];
    const intervals = Array.isArray(attrs.fuel_consumption_intervals) ? attrs.fuel_consumption_intervals : [];
    const fuelStats = this._fuelReceiptStats(receipts);
    return {
      vehicle,
      key: vehicle.vehicle_id || vehicle.key || vehicle.label,
      label: vehicle.label || "Autovehicul",
      plate: vehicle.plate || "",
      yearCost: this._toNumber(this._entityValue(yearSensor)),
      monthCost: this._toNumber(this._entityValue(monthSensor)),
      averageConsumption: this._entityValue(consumptionSensor),
      latestReceipt: this._latestFuelReceipt(receipts),
      receipts,
      intervals,
      ...fuelStats,
    };
  }

  _fuelReceiptStats(receipts) {
    const now = new Date();
    const currentYear = now.getFullYear();
    const currentMonth = now.getMonth() + 1;
    const stats = {
      yearQuantity: 0,
      monthQuantity: 0,
      yearUnitCostBase: 0,
      monthUnitCostBase: 0,
      yearReceipts: 0,
      monthReceipts: 0,
    };

    for (const receipt of Array.isArray(receipts) ? receipts : []) {
      if (!receipt || typeof receipt !== "object") continue;
      const dateParts = this._dateParts(receipt.date);
      if (!dateParts || dateParts.year !== currentYear) continue;
      const quantity = this._toNumber(receipt.quantity);
      const totalCost = this._toNumber(receipt.total_cost);
      if (quantity > 0) {
        stats.yearQuantity += quantity;
        stats.yearUnitCostBase += totalCost;
      }
      stats.yearReceipts += 1;
      if (dateParts.month === currentMonth) {
        if (quantity > 0) {
          stats.monthQuantity += quantity;
          stats.monthUnitCostBase += totalCost;
        }
        stats.monthReceipts += 1;
      }
    }

    stats.yearQuantity = Math.round(stats.yearQuantity * 1000) / 1000;
    stats.monthQuantity = Math.round(stats.monthQuantity * 1000) / 1000;
    stats.yearAverageUnitPrice = stats.yearQuantity > 0 ? stats.yearUnitCostBase / stats.yearQuantity : 0;
    stats.monthAverageUnitPrice = stats.monthQuantity > 0 ? stats.monthUnitCostBase / stats.monthQuantity : 0;
    return stats;
  }

  _dateParts(value) {
    const iso = String(value || "").trim().match(/^(\d{4})-(\d{2})-(\d{2})(?:[T\s].*)?$/);
    if (iso) return { year: Number(iso[1]), month: Number(iso[2]), day: Number(iso[3]) };

    const ro = String(value || "").trim().match(/^(\d{1,2})[\/.](\d{1,2})[\/.](\d{4})(?:\s.*)?$/);
    if (ro) return { year: Number(ro[3]), month: Number(ro[2]), day: Number(ro[1]) };

    return null;
  }

  _formatDateInputValue(value) {
    return this._parseDateInputValue(value || "");
  }

  _parseDateInputValue(value) {
    const text = String(value || "").trim();
    if (!text) return "";

    const iso = text.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T\s].*)?$/);
    if (iso) return `${iso[1]}-${iso[2]}-${iso[3]}`;

    const ro = text.match(/^(\d{1,2})[\/.](\d{1,2})[\/.](\d{4})(?:\s.*)?$/);
    if (ro) {
      const day = ro[1].padStart(2, "0");
      const month = ro[2].padStart(2, "0");
      return `${ro[3]}-${month}-${day}`;
    }

    return text;
  }

  _formDate(data, name) {
    return this._parseDateInputValue((data.get(name) || "").toString());
  }

  _latestFuelReceipt(receipts) {
    const items = Array.isArray(receipts) ? receipts.filter((receipt) => receipt && typeof receipt === "object") : [];
    if (!items.length) return null;
    return [...items].sort((a, b) => {
      const dateCompare = String(b.date || "").localeCompare(String(a.date || ""));
      if (dateCompare) return dateCompare;
      return this._toNumber(b.km) - this._toNumber(a.km);
    })[0];
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
          ${this._renderCostSummaryCard("An curent", summary.yearCost, `${this._formatNumber(summary.yearQuantity, 2)} L/kWh · ${summary.yearReceipts} bonuri`)}
          ${this._renderCostSummaryCard("Luna curentă", summary.monthCost, `${this._formatNumber(summary.monthQuantity, 2)} L/kWh · ${summary.monthReceipts} bonuri`)}
          ${this._renderCostSummaryCard("Preț mediu", summary.yearAverageUnitPrice ? `${this._formatNumber(summary.yearAverageUnitPrice, 2)} RON/unitate` : "—", "anul curent")}
          ${this._renderCostSummaryCard("Consum mediu", summary.averageConsumption && summary.averageConsumption !== "unknown" && summary.averageConsumption !== "unavailable" ? `${summary.averageConsumption} L/100 km` : "—", latestInterval ? `${latestInterval.distance_km} km · ${latestInterval.liters} L · ${this._formatMoney(latestInterval.cost)}` : "necalculat")}
          ${summary.latestReceipt ? this._renderCostSummaryCard("Ultimul bon", this._formatMoney(summary.latestReceipt.total_cost), `${this._formatDateForDisplay(summary.latestReceipt.date || "")} · ${summary.latestReceipt.quantity || ""} ${summary.latestReceipt.unit || "L"}`) : this._renderCostSummaryCard("Ultimul bon", "—", "nu există")}
        </div>
        ${this._renderFuelConsumptionHint(summary)}
        ${open ? this._renderFuelReceiptForm(summary.vehicle) : ""}
        ${message ? `<div class="cmr-message">${this._escape(message)}</div>` : ""}
        ${this._renderFuelReceipts(summary)}
      </div>
    `;
  }

  _renderFuelConsumptionHint(summary) {
    const receipts = Array.isArray(summary.receipts) ? summary.receipts : [];
    const intervals = Array.isArray(summary.intervals) ? summary.intervals : [];
    if (!receipts.length || intervals.length) return "";
    const fullCount = receipts.filter((receipt) => receipt && receipt.full_tank && (receipt.unit || "L") === "L").length;
    const message = fullCount < 2
      ? "Consum mediu necalculat: sunt necesare cel puțin două alimentări marcate „Plin făcut”."
      : "Consum mediu necalculat încă: verifică ordinea kilometrajului și alimentările marcate „Plin făcut”.";
    return `<div class="cmr-info-note">${this._escape(message)}</div>`;
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
          <label class="cmr-field"><span>Data alimentării</span><input type="date" name="date" value="${this._escape(this._formatDateInputValue(draft.date || today))}"></label>
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
    const latestReceipts = receipts.slice(0, 10);
    return `<div class="cmr-recent-title">Ultimele alimentări</div><div class="cmr-cost-list">${latestReceipts.map((receipt) => {
      const receiptId = receipt.receipt_id || "";
      const isEditing = receiptId && this._fuelReceiptEditOpen.has(receiptId);
      return `
      <div class="cmr-cost-item cmr-cost-item-with-actions">
        <div class="cmr-cost-item-main">
          <div class="cmr-cost-item-title">${this._escape(receipt.fuel_type_label || "Combustibil")} <span>${this._escape(receipt.date || "")}</span></div>
          <div class="cmr-row-muted">${this._escape([receipt.km ? `${receipt.km} km` : "", receipt.quantity ? `${receipt.quantity} ${receipt.unit || "L"}` : "", receipt.unit_price ? `${receipt.unit_price} RON/${receipt.unit || "L"}` : "", receipt.full_tank ? "plin" : "parțial", receipt.station || ""].filter(Boolean).join(" · "))}</div>
        </div>
        <div class="cmr-cost-item-side">
          <div class="cmr-cost-item-value">${this._formatMoney(receipt.total_cost)}</div>
          <div class="cmr-inline-actions">
            <button class="cmr-mini-action" type="button" data-action="toggle-edit-fuel-receipt" data-receipt-id="${this._escape(receiptId)}" data-vehicle="${this._escape(summary.key)}">${isEditing ? "Renunță" : "Editează"}</button>
            <button class="cmr-mini-action cmr-danger" type="button" data-action="delete-fuel-receipt" data-receipt-id="${this._escape(receiptId)}" data-vehicle="${this._escape(summary.key)}" data-receipt-label="${this._escape(`${this._formatDateForDisplay(receipt.date) || "fără dată"} · ${receipt.fuel_type_label || "Combustibil"} · ${this._formatMoney(receipt.total_cost)}`)}">Șterge</button>
          </div>
        </div>
        ${isEditing ? this._renderFuelReceiptEditForm(summary.vehicle, receipt) : ""}
      </div>`;
    }).join("")}</div>`;
  }

  _renderFuelReceiptEditForm(vehicle, receipt) {
    const vehicleKey = vehicle.vehicle_id || vehicle.key || vehicle.label || "";
    const receiptId = receipt.receipt_id || "";
    const draft = this._fuelReceiptEditDrafts[receiptId] || {};
    const fuelProfile = this._vehicleFuelProfile(vehicle);
    const selectedFuelType = draft.fuel_type || receipt.fuel_type || "";
    const fuelOptions = this._fuelTypeOptions(fuelProfile, selectedFuelType);
    const quantity = draft.quantity ?? receipt.quantity ?? "";
    const totalCost = draft.total_cost ?? receipt.total_cost ?? "";
    const fullTank = Object.prototype.hasOwnProperty.call(draft, "full_tank") ? draft.full_tank : !!receipt.full_tank;
    return `
      <form class="cmr-history-form cmr-inline-edit-form" data-form="fuel-receipt-edit" data-receipt-id="${this._escape(receiptId)}" data-vehicle="${this._escape(vehicleKey)}" data-vehicle-ref="${this._escape(vehicle.vehicle_id || vehicle.plate || vehicle.label || vehicle.key || "")}">
        <div class="cmr-add-grid">
          <label class="cmr-field"><span>Data alimentării</span><input type="date" name="date" value="${this._escape(this._formatDateInputValue(draft.date ?? receipt.date ?? ""))}"></label>
          <label class="cmr-field"><span>Kilometraj bord</span><input type="number" name="km" min="1" step="1" required value="${this._escape(draft.km ?? receipt.km ?? "")}"></label>
          <label class="cmr-field"><span>Tip combustibil</span><select name="fuel_type" required>${fuelOptions}</select></label>
          <label class="cmr-field"><span>Litri / kWh</span><input type="number" name="quantity" min="0.001" step="0.001" required value="${this._escape(quantity)}"></label>
          <label class="cmr-field"><span>Valoare bon</span><input type="number" name="total_cost" min="0.01" step="0.01" required value="${this._escape(totalCost)}"></label>
          <label class="cmr-field"><span>Stație</span><input type="text" name="station" value="${this._escape(draft.station ?? receipt.station ?? "")}" placeholder="opțional"></label>
        </div>
        <label class="cmr-check"><input type="checkbox" name="full_tank" ${fullTank ? "checked" : ""}> Plin făcut</label>
        <label class="cmr-field"><span>Observații</span><textarea name="notes" rows="2">${this._escape(draft.notes ?? receipt.notes ?? "")}</textarea></label>
        <div class="cmr-add-actions">
          <button class="cmr-action" type="submit" ${this._fuelReceiptBusy === receiptId ? "disabled" : ""}>${this._fuelReceiptBusy === receiptId ? "Se salvează..." : "Salvează modificările"}</button>
        </div>
      </form>
    `;
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

  _renderTiresTab(vehicles) {
    if (!vehicles.length) return this._renderEmpty();

    const allSummaries = vehicles.map((vehicle) => this._tireSummaryForVehicle(vehicle));
    if (this._tireVehicleFilter !== "all" && !allSummaries.some((summary) => summary.key === this._tireVehicleFilter)) {
      this._tireVehicleFilter = "all";
    }
    const summaries = this._tireVehicleFilter === "all"
      ? allSummaries
      : allSummaries.filter((summary) => summary.key === this._tireVehicleFilter);
    const totalSets = summaries.reduce((sum, item) => sum + item.sets.length, 0);
    const mountedSets = summaries.reduce((sum, item) => sum + item.mountedSets.length, 0);
    const totalAnnual = summaries.reduce((sum, item) => sum + item.yearCost, 0);
    return `
      <section class="cmr-costs-panel">
        <div class="cmr-section-head cmr-fuel-head">
          <div>
            <div class="cmr-section-title">Anvelope</div>
            <div class="cmr-row-muted">Seturi vară / iarnă / all season, DOT, km, jante, cost și loc depozitare</div>
          </div>
          <div class="cmr-fuel-head-actions">
            ${this._renderTireVehicleFilter(allSummaries)}
          </div>
        </div>
        <div class="cmr-cost-summary-grid">
          ${this._renderCostSummaryCard("Seturi salvate", `${totalSets}`, this._tireVehicleFilter === "all" ? "Total seturi anvelope" : "Seturi pentru mașina selectată")}
          ${this._renderCostSummaryCard("Montate acum", `${mountedSets}`, "Seturi marcate ca montate")}
          ${this._renderCostSummaryCard("Cost an curent", totalAnnual, "După data cumpărării")}
        </div>
        ${summaries.map((summary) => this._renderTireVehiclePanel(summary)).join("")}
      </section>
    `;
  }

  _renderTireVehicleFilter(summaries) {
    if (!Array.isArray(summaries) || summaries.length <= 1) return "";
    return `
      <label class="cmr-fuel-filter">
        <span>Mașină</span>
        <select data-action="tire-filter">
          <option value="all" ${this._tireVehicleFilter === "all" ? "selected" : ""}>Toate</option>
          ${summaries.map((summary) => `<option value="${this._escape(summary.key)}" ${this._tireVehicleFilter === summary.key ? "selected" : ""}>${this._escape(summary.label)}</option>`).join("")}
        </select>
      </label>
    `;
  }

  _tireSummaryForVehicle(vehicle) {
    const attrs = this._vehicleStatusAttributes(vehicle);
    const sets = Array.isArray(attrs.tire_sets) ? attrs.tire_sets : [];
    const currentYear = new Date().getFullYear();
    const yearCost = sets.reduce((sum, item) => {
      const parts = this._dateParts(item.purchase_date);
      return sum + (parts && parts.year === currentYear ? this._toNumber(item.cost) : 0);
    }, 0);
    return {
      vehicle,
      key: vehicle.vehicle_id || vehicle.key || vehicle.label,
      label: vehicle.label || "Autovehicul",
      plate: vehicle.plate || "",
      sets,
      mountedSets: sets.filter((item) => item && item.installed),
      yearCost,
    };
  }

  _renderTireVehiclePanel(summary) {
    const open = this._tireFormOpen.has(summary.key);
    const message = this._tireSetMessage[summary.key] || "";
    return `
      <div class="cmr-cost-section">
        <div class="cmr-section-head">
          <div>
            <div class="cmr-section-title">${this._escape(summary.label)}</div>
            <div class="cmr-row-muted">${this._escape(summary.plate || "")}</div>
          </div>
          <button class="cmr-mini-action" type="button" data-action="toggle-tire-form" data-vehicle="${this._escape(summary.key)}">${open ? "Închide" : "Adaugă set"}</button>
        </div>
        <div class="cmr-cost-summary-grid cmr-fuel-summary-grid">
          ${this._renderCostSummaryCard("Seturi", `${summary.sets.length}`, `${summary.mountedSets.length} montate acum`)}
          ${this._renderCostSummaryCard("Cost an curent", summary.yearCost, "după data cumpărării")}
          ${summary.mountedSets[0] ? this._renderCostSummaryCard("Montate", summary.mountedSets[0].tire_type_label || "—", `${summary.mountedSets[0].size || ""} ${summary.mountedSets[0].brand_model || ""}`) : this._renderCostSummaryCard("Montate", "—", "nu este marcat niciun set")}
        </div>
        ${open ? this._renderTireSetForm(summary.vehicle) : ""}
        ${message ? `<div class="cmr-message">${this._escape(message)}</div>` : ""}
        ${this._renderTireSets(summary)}
      </div>
    `;
  }

  _renderTireMini(vehicle) {
    const summary = this._tireSummaryForVehicle(vehicle);
    if (!summary.sets.length) return "";
    return `
      <div class="cmr-section">
        <div class="cmr-section-title">Anvelope</div>
        ${summary.mountedSets.length
          ? summary.mountedSets.map((item) => this._renderRow("Montate", `${item.tire_type_label || "—"} · ${item.size || "dimensiune necompletată"}${item.wheel_mount_type_label ? ` · ${item.wheel_mount_type_label}` : ""}`, item.brand_model || "", item.dot ? `DOT ${item.dot}` : "", "")).join("")
          : this._renderRow("Montate", "Niciun set marcat ca montat", "", "", "")}
      </div>
    `;
  }

  _tireTypeOptions(selected) {
    const options = [["summer", "Vară"], ["winter", "Iarnă"], ["all_season", "All season"]];
    const selectedValue = selected || "summer";
    return options.map(([value, label]) => `<option value="${value}" ${value === selectedValue ? "selected" : ""}>${label}</option>`).join("");
  }

  _tireMountTypeOptions(selected) {
    const options = [["tires_only", "Doar cauciucuri"], ["on_rims", "Pe jante"]];
    const selectedValue = selected || "tires_only";
    return options.map(([value, label]) => `<option value="${value}" ${value === selectedValue ? "selected" : ""}>${label}</option>`).join("");
  }

  _renderTireSetForm(vehicle) {
    const vehicleKey = vehicle.vehicle_id || vehicle.key || vehicle.label || "";
    const draft = this._tireSetDrafts[vehicleKey] || {};
    const today = new Date().toISOString().slice(0, 10);
    return `
      <form class="cmr-history-form" data-form="tire-set" data-vehicle="${this._escape(vehicleKey)}" data-vehicle-ref="${this._escape(vehicle.vehicle_id || vehicle.plate || vehicle.label || vehicle.key || "")}">
        <div class="cmr-add-grid">
          <label class="cmr-field"><span>Tip anvelope</span><select name="tire_type">${this._tireTypeOptions(draft.tire_type || "summer")}</select></label>
          <label class="cmr-field"><span>Marcă / model</span><input type="text" name="brand_model" value="${this._escape(draft.brand_model || "")}" placeholder="ex. Michelin Primacy 4"></label>
          <label class="cmr-field"><span>Dimensiune</span><input type="text" name="size" value="${this._escape(draft.size || "")}" placeholder="ex. 245/45 R18"></label>
          <label class="cmr-field"><span>DOT</span><input type="text" name="dot" value="${this._escape(draft.dot || "")}" placeholder="ex. 3523"></label>
          <label class="cmr-field"><span>Nr. bucăți</span><input type="number" name="quantity" min="1" max="12" step="1" value="${this._escape(draft.quantity || "4")}"></label>
          <label class="cmr-field"><span>Montaj</span><select name="wheel_mount_type">${this._tireMountTypeOptions(draft.wheel_mount_type || "tires_only")}</select></label>
          <label class="cmr-field"><span>Data cumpărării</span><input type="date" name="purchase_date" value="${this._escape(this._formatDateInputValue(draft.purchase_date || today))}"></label>
          <label class="cmr-field"><span>Data montării</span><input type="date" name="last_mount_date" value="${this._escape(this._formatDateInputValue(draft.last_mount_date || ""))}"></label>
          <label class="cmr-field"><span>Km la montare</span><input type="number" name="last_mount_km" min="0" step="1" value="${this._escape(draft.last_mount_km || "0")}"></label>
          <label class="cmr-field"><span>Km parcurși cu setul</span><input type="number" name="total_km" min="0" step="1" value="${this._escape(draft.total_km || "0")}"></label>
          <label class="cmr-field"><span>Cost</span><input type="number" name="cost" min="0" step="0.01" value="${this._escape(draft.cost || "0")}"></label>
          <label class="cmr-field"><span>Depozitare</span><input type="text" name="storage_location" value="${this._escape(draft.storage_location || "")}" placeholder="acasă / service"></label>
          <label class="cmr-field"><span>Presiune față</span><input type="text" name="pressure_front" value="${this._escape(draft.pressure_front || "")}" placeholder="ex. 2.4 bar"></label>
          <label class="cmr-field"><span>Presiune spate</span><input type="text" name="pressure_rear" value="${this._escape(draft.pressure_rear || "")}" placeholder="ex. 2.3 bar"></label>
        </div>
        <label class="cmr-check"><input type="checkbox" name="installed" ${draft.installed ? "checked" : ""}> Set montat acum</label>
        <label class="cmr-field"><span>Observații</span><textarea name="notes" rows="2">${this._escape(draft.notes || "")}</textarea></label>
        <div class="cmr-add-actions"><button class="cmr-action" type="submit" ${this._tireSetBusy === vehicleKey ? "disabled" : ""}>${this._tireSetBusy === vehicleKey ? "Se salvează..." : "Salvează setul"}</button></div>
      </form>
    `;
  }

  _renderTireSets(summary) {
    const sets = Array.isArray(summary.sets) ? summary.sets : [];
    if (!sets.length) return `<div class="cmr-history-empty">Nu există seturi de anvelope salvate pentru acest autovehicul.</div>`;
    return `<div class="cmr-cost-list">${sets.map((item) => this._renderTireSetItem(summary, item)).join("")}</div>`;
  }

  _renderTireSetItem(summary, item) {
    const setId = item.set_id || "";
    const editOpen = setId && this._tireSetEditOpen.has(setId);
    const title = [item.tire_type_label || "Anvelope", item.brand_model || "", item.size || ""].filter(Boolean).join(" · ");
    const meta = [item.dot ? `DOT ${item.dot}` : "", item.quantity ? `${item.quantity} buc.` : "", item.wheel_mount_type_label || "", item.total_km ? `${item.total_km} km` : "", item.installed ? "montate acum" : "depozitate", item.storage_location || ""].filter(Boolean).join(" · ");
    return `
      <div class="cmr-cost-item cmr-cost-item-block">
        <div class="cmr-cost-item-main">
          <div class="cmr-cost-item-title">${this._escape(title || "Set anvelope")} ${item.installed ? `<span>montat</span>` : ""}</div>
          <div class="cmr-row-muted">${this._escape(meta)}</div>
          ${item.notes ? `<div class="cmr-history-notes">${this._escape(item.notes)}</div>` : ""}
        </div>
        <div class="cmr-cost-item-side">
          <div class="cmr-cost-item-value">${this._formatMoney(item.cost)}</div>
          <div class="cmr-inline-actions">
            <button class="cmr-mini-action" type="button" data-action="toggle-edit-tire-set" data-set-id="${this._escape(setId)}">${editOpen ? "Renunță" : "Editează"}</button>
            <button class="cmr-mini-action cmr-danger" type="button" data-action="delete-tire-set" data-set-id="${this._escape(setId)}" data-vehicle="${this._escape(summary.key)}" data-tire-label="${this._escape(title)}">Șterge</button>
          </div>
        </div>
        ${editOpen ? this._renderTireSetEditForm(summary.vehicle, item) : ""}
      </div>`;
  }

  _renderTireSetEditForm(vehicle, item) {
    const vehicleKey = vehicle.vehicle_id || vehicle.key || vehicle.label || "";
    const setId = item.set_id || "";
    const draft = this._tireSetEditDrafts[setId] || {};
    const value = (key, fallback = "") => draft[key] ?? item[key] ?? fallback;
    const installed = Object.prototype.hasOwnProperty.call(draft, "installed") ? draft.installed : !!item.installed;
    return `
      <form class="cmr-history-form cmr-inline-edit-form" data-form="tire-set-edit" data-set-id="${this._escape(setId)}" data-vehicle="${this._escape(vehicleKey)}" data-vehicle-ref="${this._escape(vehicle.vehicle_id || vehicle.plate || vehicle.label || vehicle.key || "")}">
        <div class="cmr-add-grid">
          <label class="cmr-field"><span>Tip anvelope</span><select name="tire_type">${this._tireTypeOptions(value("tire_type", "summer"))}</select></label>
          <label class="cmr-field"><span>Marcă / model</span><input type="text" name="brand_model" value="${this._escape(value("brand_model"))}"></label>
          <label class="cmr-field"><span>Dimensiune</span><input type="text" name="size" value="${this._escape(value("size"))}"></label>
          <label class="cmr-field"><span>DOT</span><input type="text" name="dot" value="${this._escape(value("dot"))}"></label>
          <label class="cmr-field"><span>Nr. bucăți</span><input type="number" name="quantity" min="1" max="12" step="1" value="${this._escape(value("quantity", "4"))}"></label>
          <label class="cmr-field"><span>Montaj</span><select name="wheel_mount_type">${this._tireMountTypeOptions(value("wheel_mount_type", "tires_only"))}</select></label>
          <label class="cmr-field"><span>Data cumpărării</span><input type="date" name="purchase_date" value="${this._escape(this._formatDateInputValue(value("purchase_date")))}"></label>
          <label class="cmr-field"><span>Data montării</span><input type="date" name="last_mount_date" value="${this._escape(this._formatDateInputValue(value("last_mount_date")))}"></label>
          <label class="cmr-field"><span>Km la montare</span><input type="number" name="last_mount_km" min="0" step="1" value="${this._escape(value("last_mount_km", "0"))}"></label>
          <label class="cmr-field"><span>Km parcurși cu setul</span><input type="number" name="total_km" min="0" step="1" value="${this._escape(value("total_km", "0"))}"></label>
          <label class="cmr-field"><span>Cost</span><input type="number" name="cost" min="0" step="0.01" value="${this._escape(value("cost", "0"))}"></label>
          <label class="cmr-field"><span>Depozitare</span><input type="text" name="storage_location" value="${this._escape(value("storage_location"))}"></label>
          <label class="cmr-field"><span>Presiune față</span><input type="text" name="pressure_front" value="${this._escape(value("pressure_front"))}"></label>
          <label class="cmr-field"><span>Presiune spate</span><input type="text" name="pressure_rear" value="${this._escape(value("pressure_rear"))}"></label>
        </div>
        <label class="cmr-check"><input type="checkbox" name="installed" ${installed ? "checked" : ""}> Set montat acum</label>
        <label class="cmr-field"><span>Observații</span><textarea name="notes" rows="2">${this._escape(value("notes"))}</textarea></label>
        <div class="cmr-add-actions"><button class="cmr-action" type="submit" ${this._tireSetBusy === setId ? "disabled" : ""}>${this._tireSetBusy === setId ? "Se salvează..." : "Salvează modificările"}</button></div>
      </form>
    `;
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

  _formatNumber(value, decimals = 2) {
    const number = this._toNumber(value);
    if (!Number.isFinite(number)) return "0";
    return number.toLocaleString("ro-RO", {
      minimumFractionDigits: number % 1 === 0 ? 0 : decimals,
      maximumFractionDigits: decimals,
    });
  }

  _costSummaryForVehicle(vehicle) {
    const annualSensor = this._findSensorByName(vehicle, ["costuri", "anul", "curent"]);
    const upcoming30Sensor = this._findSensorByName(vehicle, ["cheltuieli", "urmatoarele", "30", "zile"]);
    const upcoming90Sensor = this._findSensorByName(vehicle, ["cheltuieli", "urmatoarele", "90", "zile"]);
    const items30 = this._costItemsFromSensor(upcoming30Sensor);
    const items90 = this._costItemsFromSensor(upcoming90Sensor);

    return {
      vehicle,
      key: vehicle.vehicle_id || vehicle.key || vehicle.label,
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

  _renderLicenseLockedVehicle(vehicle, index) {
    const label = index ? `Autovehicul suplimentar #${index}` : "Autovehicul suplimentar";
    return `
      <section class="cmr-vehicle cmr-license-locked-vehicle">
        <div class="cmr-locked-head">
          <div class="cmr-locked-icon"><ha-icon icon="mdi:lock-outline"></ha-icon></div>
          <div>
            <div class="cmr-vehicle-title">${this._escape(label)}</div>
            <div class="cmr-plate">Dezactivat fără licență activă</div>
          </div>
        </div>
        <div class="cmr-license-locked-body">
          Datele acestui autovehicul sunt păstrate local, dar afișarea și funcțiile lui sunt blocate până la activarea unei licențe valide.
        </div>
        <div class="cmr-license-locked-actions">
          <button class="cmr-mode" data-action="open-license-tab" type="button">Activează licența</button>
        </div>
      </section>
    `;
  }

  _renderDashboard(vehicle, summary) {
    const expanded = this._showDetails || this._expandedVehicles.has(vehicle.key);
    const premiumAccess = this._licenseAllowsPremiumFeatures();
    const detailsHtml = premiumAccess
      ? `${this._renderMaintenance(vehicle)}${this._renderFuelMini(vehicle)}${this._renderTireMini(vehicle)}${this._renderConsumables(vehicle)}${this._renderServiceHistory(vehicle)}${this._showDetails ? this._renderRovinietaDetails(vehicle) : ""}`
      : `${this._renderMaintenance(vehicle)}${this._renderLegalDetails(summary)}${this._renderRovinietaDetails(vehicle)}${this._renderFreeModeNotice()}`;

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
      ${expanded ? `<div class="cmr-details">${detailsHtml}</div>` : ""}
    `;
  }

  _renderFreeModeNotice() {
    return `
      <div class="cmr-section cmr-free-mode-section">
        <div class="cmr-section-title">Mod gratuit</div>
        <div class="cmr-row-muted">
          Sunt disponibile doar revizia, RCA, CASCO, ITP și rovinieta pentru primul autovehicul. Costurile, combustibilul, anvelopele, siguranța, bateria, istoricul intervențiilor și notificările sunt disponibile doar cu licență activă sau în perioada de test.
        </div>
      </div>
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
        <div class="cmr-tile-sub">${this._escape(this._formatDisplayValue(status || sub || "neconfigurat"))}</div>
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
      ? `<button class="cmr-mini-action cmr-danger" data-action="delete-service-record" data-record-id="${this._escape(recordId)}" data-vehicle="${this._escape(vehicleKey)}" data-record-title="${this._escape(title)}" data-updates-maintenance="${record.update_maintenance ? "1" : "0"}" data-restored="${restored ? "1" : "0"}">Șterge</button>`
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
            <input type="date" name="date" value="${this._escape(this._formatDateInputValue(draft.date || today))}">
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
      return /rovinieta.*(incepe la|expira la|cost estimat)/.test(name);
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
    const type = domain === "date" ? "date" : domain === "number" ? "number" : "text";
    const inputValue = domain === "date" ? this._formatDateInputValue(value) : value;
    const placeholder = "";
    return `
      <label class="cmr-field">
        <span>${this._escape(label)}</span>
        <input type="${type}" value="${this._escape(inputValue)}" data-entity="${entity.entityId}" data-domain="${domain}"${placeholder}>
      </label>
    `;
  }

  _renderRow(label, value, middle, right, cls) {
    return `
      <div class="cmr-row ${cls || ""}">
        <div class="cmr-row-label">${this._escape(label)}</div>
        <div class="cmr-row-value">${this._escape(this._formatDisplayValue(value || "—"))}</div>
        ${middle ? `<div class="cmr-row-muted">${this._escape(this._formatDisplayValue(middle))}</div>` : ""}
        ${right ? `<div class="cmr-row-muted">${this._escape(this._formatDisplayValue(right))}</div>` : ""}
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

  async _applyLicense(value) {
    const textEntity = this._licenseEntity("text", "cod_licenta_noua");
    const buttonEntity = this._licenseEntity("button", "aplica_licenta");

    if (!textEntity || !buttonEntity) {
      this._licenseMessage = "Entitățile de licențiere nu sunt disponibile încă. Fă un restart Home Assistant după actualizare.";
      this.render();
      return;
    }

    try {
      this._licenseMessage = "Se validează licența...";
      this.render();
      await this._hass.callService("text", "set_value", { value: value || "TRIAL" }, { entity_id: textEntity.entity_id });
      await this._hass.callService("button", "press", {}, { entity_id: buttonEntity.entity_id });
      this._licenseDraft = value || "TRIAL";
      this._licenseMessage = "Licența a fost trimisă pentru validare. Statusul se actualizează imediat ce Home Assistant reîmprospătează senzorii.";
      await this._refreshLicenseEntities();
    } catch (error) {
      this._licenseMessage = error?.message || "Nu am putut aplica licența.";
    }

    this.render();
  }

  async _refreshLicenseEntities() {
    const refreshButton = this._licenseRefreshButtonEntity();
    const entityIds = [
      this._licenseEntity("sensor", "status_licenta")?.entity_id,
      this._licenseEntity("sensor", "plan_licenta")?.entity_id,
      this._licenseEntity("sensor", "valabila_pana_la")?.entity_id,
      this._licenseEntity("sensor", "ultima_verificare_licenta")?.entity_id,
      this._licenseEntity("sensor", "cont_licenta")?.entity_id,
      this._licenseEntity("sensor", "cod_licenta_mascat")?.entity_id,
      this._licenseEntity("sensor", "mesaj_licenta")?.entity_id,
    ].filter(Boolean);

    try {
      this._licenseMessage = "Se verifică licența online...";
      this.render();

      if (this._hass.services?.car_manager_romania?.refresh_license_status) {
        await this._hass.callService("car_manager_romania", "refresh_license_status", {});
        this._licenseMessage = "Statusul licenței a fost verificat online.";
      } else if (refreshButton?.entity_id) {
        await this._hass.callService("button", "press", {}, { entity_id: refreshButton.entity_id });
        this._licenseMessage = "Statusul licenței a fost verificat online.";
      } else {
        throw new Error("Serviciul de verificare online a licenței nu este disponibil. Fă restart Home Assistant după actualizare.");
      }
    } catch (error) {
      this._licenseMessage = error?.message || "Nu am putut verifica licența.";
    }

    if (entityIds.length) {
      try {
        await this._hass.callService("homeassistant", "update_entity", { entity_id: entityIds });
      } catch (_error) {
        // Senzorii primesc oricum update prin dispatcher; acest update este doar un fallback vizual.
      }
    }
  }

  _attachEvents() {
    this.querySelectorAll(".cmr-brand-icon").forEach((image) => {
      image.addEventListener("error", () => image.classList.add("is-hidden"), { once: true });
    });

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

    const licenseForm = this.querySelector('form[data-form="license"]');
    licenseForm?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const input = licenseForm.querySelector('input[name="license_key"]');
      const value = (input?.value || "").toString().trim();
      this._licenseDraft = value;
      await this._applyLicense(value);
    });
    licenseForm?.addEventListener("input", () => {
      const input = licenseForm.querySelector('input[name="license_key"]');
      this._licenseDraft = (input?.value || "").toString();
    });

    this.querySelector('[data-action="license-refresh"]')?.addEventListener("click", async () => {
      await this._refreshLicenseEntities();
    });

    this.querySelectorAll('[data-action="open-license-tab"]').forEach((button) => {
      button.addEventListener("click", () => {
        this._activeTab = "license";
        this._tabHoverLabel = "";
        this.render();
      });
    });

    this.querySelectorAll('[data-action="set-tab"]').forEach((button) => {
      button.addEventListener("click", () => {
        const tab = button.dataset.tab || "vehicles";
        this._activeTab = ["costs", "fuel", "tires", "equipment", "battery", "license"].includes(tab) ? tab : "vehicles";
        this._tabHoverLabel = "";
        this.render();
      });
      button.addEventListener("mouseenter", () => {
        this._setTabHoverLabel(button.dataset.label || "");
      });
      button.addEventListener("focus", () => {
        this._setTabHoverLabel(button.dataset.label || "");
      });
      button.addEventListener("mouseleave", () => {
        this._clearTabHoverLabel();
      });
      button.addEventListener("blur", () => {
        this._clearTabHoverLabel();
      });
    });

    this.querySelector('[data-action="fuel-filter"]')?.addEventListener("change", (event) => {
      this._fuelVehicleFilter = event.currentTarget.value || "all";
      this.render();
    });

    this.querySelector('[data-action="tire-filter"]')?.addEventListener("change", (event) => {
      this._tireVehicleFilter = event.currentTarget.value || "all";
      this.render();
    });

    this.querySelector('[data-action="equipment-filter"]')?.addEventListener("change", (event) => {
      this._equipmentVehicleFilter = event.currentTarget.value || "all";
      this.render();
    });

    this.querySelector('[data-action="battery-filter"]')?.addEventListener("change", (event) => {
      this._batteryVehicleFilter = event.currentTarget.value || "all";
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

    this.querySelectorAll('button[data-action="toggle-tire-form"]').forEach((button) => {
      button.addEventListener("click", () => {
        const key = button.dataset.vehicle;
        if (!key) return;
        if (this._tireFormOpen.has(key)) this._tireFormOpen.delete(key); else this._tireFormOpen.add(key);
        this.render();
      });
    });

    this.querySelectorAll('form[data-form="tire-set"]').forEach((form) => {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        this._captureTireSetDraft(form);
        this._inputEditing = false;
        this._addTireSet(form);
      });
      form.addEventListener("input", () => this._captureTireSetDraft(form));
      form.addEventListener("change", () => this._captureTireSetDraft(form));
    });

    this.querySelectorAll('button[data-action="toggle-edit-tire-set"]').forEach((button) => {
      button.addEventListener("click", () => {
        const setId = button.dataset.setId;
        if (!setId) return;
        if (this._tireSetEditOpen.has(setId)) this._tireSetEditOpen.delete(setId); else this._tireSetEditOpen.add(setId);
        this.render();
      });
    });

    this.querySelectorAll('form[data-form="tire-set-edit"]').forEach((form) => {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        this._captureTireSetEditDraft(form);
        this._inputEditing = false;
        this._updateTireSet(form);
      });
      form.addEventListener("input", () => this._captureTireSetEditDraft(form));
      form.addEventListener("change", () => this._captureTireSetEditDraft(form));
    });

    this.querySelectorAll('button[data-action="delete-tire-set"]').forEach((button) => {
      button.addEventListener("click", () => this._deleteTireSet(button.dataset.setId, button.dataset.vehicle, button.dataset.tireLabel));
    });

    this.querySelectorAll('button[data-action="toggle-equipment-form"]').forEach((button) => {
      button.addEventListener("click", () => {
        const key = button.dataset.vehicle;
        if (!key) return;
        if (this._equipmentFormOpen.has(key)) this._equipmentFormOpen.delete(key); else this._equipmentFormOpen.add(key);
        this.render();
      });
    });

    this.querySelectorAll('form[data-form="equipment-item"]').forEach((form) => {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        this._captureEquipmentDraft(form);
        this._inputEditing = false;
        this._addEquipmentItem(form);
      });
      form.addEventListener("input", () => this._captureEquipmentDraft(form));
      form.addEventListener("change", () => this._captureEquipmentDraft(form));
    });

    this.querySelectorAll('button[data-action="toggle-edit-equipment-item"]').forEach((button) => {
      button.addEventListener("click", () => {
        const itemId = button.dataset.itemId;
        if (!itemId) return;
        if (this._equipmentEditOpen.has(itemId)) this._equipmentEditOpen.delete(itemId); else this._equipmentEditOpen.add(itemId);
        this.render();
      });
    });

    this.querySelectorAll('form[data-form="equipment-item-edit"]').forEach((form) => {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        this._captureEquipmentEditDraft(form);
        this._inputEditing = false;
        this._updateEquipmentItem(form);
      });
      form.addEventListener("input", () => this._captureEquipmentEditDraft(form));
      form.addEventListener("change", () => this._captureEquipmentEditDraft(form));
    });

    this.querySelectorAll('button[data-action="delete-equipment-item"]').forEach((button) => {
      button.addEventListener("click", () => this._deleteEquipmentItem(button.dataset.itemId, button.dataset.vehicle, button.dataset.equipmentLabel));
    });

    this.querySelectorAll('button[data-action="prepare-missing-equipment"]').forEach((button) => {
      button.addEventListener("click", () => this._prepareMissingEquipment(button.dataset.vehicle, button.dataset.equipmentType));
    });

    this.querySelectorAll('button[data-action="ignore-equipment-type"]').forEach((button) => {
      button.addEventListener("click", () => this._ignoreEquipmentType(button.dataset.vehicle, button.dataset.vehicleRef, button.dataset.equipmentType, button.dataset.equipmentLabel));
    });

    this.querySelectorAll('button[data-action="reactivate-equipment-type"]').forEach((button) => {
      button.addEventListener("click", () => this._reactivateEquipmentType(button.dataset.itemId, button.dataset.vehicle, button.dataset.equipmentLabel));
    });

    this.querySelectorAll('button[data-action="toggle-battery-form"]').forEach((button) => {
      button.addEventListener("click", () => {
        const key = button.dataset.vehicle;
        if (!key) return;
        if (this._batteryFormOpen.has(key)) this._batteryFormOpen.delete(key); else this._batteryFormOpen.add(key);
        this.render();
      });
    });

    this.querySelectorAll('form[data-form="battery-item"]').forEach((form) => {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        this._captureBatteryDraft(form);
        this._inputEditing = false;
        this._addBattery(form);
      });
      form.addEventListener("input", () => this._captureBatteryDraft(form));
      form.addEventListener("change", () => this._captureBatteryDraft(form));
    });

    this.querySelectorAll('button[data-action="toggle-edit-battery"]').forEach((button) => {
      button.addEventListener("click", () => {
        const batteryId = button.dataset.batteryId;
        if (!batteryId) return;
        if (this._batteryEditOpen.has(batteryId)) this._batteryEditOpen.delete(batteryId); else this._batteryEditOpen.add(batteryId);
        this.render();
      });
    });

    this.querySelectorAll('form[data-form="battery-item-edit"]').forEach((form) => {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        this._captureBatteryEditDraft(form);
        this._inputEditing = false;
        this._updateBattery(form);
      });
      form.addEventListener("input", () => this._captureBatteryEditDraft(form));
      form.addEventListener("change", () => this._captureBatteryEditDraft(form));
    });

    this.querySelectorAll('button[data-action="delete-battery"]').forEach((button) => {
      button.addEventListener("click", () => this._deleteBattery(button.dataset.batteryId, button.dataset.vehicle, button.dataset.batteryLabel));
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

    this.querySelectorAll('button[data-action="toggle-edit-fuel-receipt"]').forEach((button) => {
      button.addEventListener("click", () => {
        const receiptId = button.dataset.receiptId;
        if (!receiptId) return;
        if (this._fuelReceiptEditOpen.has(receiptId)) {
          this._fuelReceiptEditOpen.delete(receiptId);
        } else {
          this._fuelReceiptEditOpen.add(receiptId);
        }
        this.render();
      });
    });

    this.querySelectorAll('button[data-action="export-fuel-history"]').forEach((button) => {
      button.addEventListener("click", () => this._exportFuelHistory());
    });

    this.querySelectorAll('button[data-action="delete-fuel-receipt"]').forEach((button) => {
      button.addEventListener("click", () => this._deleteFuelReceipt(button.dataset.receiptId, button.dataset.vehicle, button.dataset.receiptLabel));
    });

    this.querySelectorAll('form[data-form="fuel-receipt-edit"]').forEach((form) => {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        this._captureFuelReceiptEditDraft(form);
        this._inputEditing = false;
        this._updateFuelReceipt(form);
      });
      form.addEventListener("input", () => this._captureFuelReceiptEditDraft(form));
      form.addEventListener("change", () => this._captureFuelReceiptEditDraft(form));
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
        title: button.dataset.recordTitle || "",
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
      date: this._formDate(data, "date"),
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


  _renderBatteryTab(vehicles) {
    if (!vehicles.length) return this._renderEmpty();

    const allSummaries = vehicles.map((vehicle) => this._batterySummaryForVehicle(vehicle));
    if (this._batteryVehicleFilter !== "all" && !allSummaries.some((summary) => summary.key === this._batteryVehicleFilter)) {
      this._batteryVehicleFilter = "all";
    }
    const summaries = this._batteryVehicleFilter === "all"
      ? allSummaries
      : allSummaries.filter((summary) => summary.key === this._batteryVehicleFilter);
    const totalItems = summaries.reduce((sum, item) => sum + item.items.length, 0);
    const installed = summaries.reduce((sum, item) => sum + (item.current ? 1 : 0), 0);
    const warnings = summaries.reduce((sum, item) => sum + item.warningCount, 0);
    const totalAnnual = summaries.reduce((sum, item) => sum + item.yearCost, 0);
    return `
      <section class="cmr-costs-panel">
        <div class="cmr-section-head cmr-fuel-head">
          <div>
            <div class="cmr-section-title">Baterie auto</div>
            <div class="cmr-row-muted">Montaj, garanție, vechime, capacitate și costuri</div>
          </div>
          <div class="cmr-fuel-head-actions">
            ${this._renderBatteryVehicleFilter(allSummaries)}
          </div>
        </div>
        <div class="cmr-cost-summary-grid">
          ${this._renderCostSummaryCard("Baterii", `${totalItems}`, this._batteryVehicleFilter === "all" ? "Total baterii salvate" : "Baterii pentru mașina selectată")}
          ${this._renderCostSummaryCard("Montate", `${installed}`, "Marcate ca montate acum")}
          ${this._renderCostSummaryCard("Alerte", `${warnings}`, warnings ? "garanție / vechime" : "fără alerte")}
          ${this._renderCostSummaryCard("Cost an curent", totalAnnual, "După data montării")}
        </div>
        ${summaries.map((summary) => this._renderBatteryVehiclePanel(summary)).join("")}
      </section>
    `;
  }

  _renderBatteryVehicleFilter(summaries) {
    if (!Array.isArray(summaries) || summaries.length <= 1) return "";
    return `
      <label class="cmr-fuel-filter">
        <span>Mașină</span>
        <select data-action="battery-filter">
          <option value="all" ${this._batteryVehicleFilter === "all" ? "selected" : ""}>Toate</option>
          ${summaries.map((summary) => `<option value="${this._escape(summary.key)}" ${this._batteryVehicleFilter === summary.key ? "selected" : ""}>${this._escape(summary.label)}</option>`).join("")}
        </select>
      </label>
    `;
  }

  _batteryTypeList() {
    return [
      ["lead_acid", "Plumb-acid clasică"],
      ["agm", "AGM"],
      ["efb", "EFB"],
      ["gel", "Gel"],
      ["lithium", "Litiu"],
      ["other", "Alt tip"],
    ];
  }

  _batteryTypeOptions(selected) {
    const selectedValue = selected || "lead_acid";
    return this._batteryTypeList().map(([value, label]) => `<option value="${value}" ${value === selectedValue ? "selected" : ""}>${label}</option>`).join("");
  }

  _batterySummaryForVehicle(vehicle) {
    const attrs = this._vehicleStatusAttributes(vehicle);
    const items = Array.isArray(attrs.battery_items) ? attrs.battery_items : [];
    const current = attrs.current_battery || items.find((item) => item && item.installed) || null;
    const currentYear = new Date().getFullYear();
    const yearCost = items.reduce((sum, item) => {
      const parts = this._dateParts(item.install_date);
      return sum + (parts && parts.year === currentYear ? this._toNumber(item.cost) : 0);
    }, 0);
    const warningStatuses = new Set(["warranty_expired", "warranty_soon", "very_old", "old", "attention", "unknown", "not_installed"]);
    return {
      vehicle,
      key: vehicle.vehicle_id || vehicle.key || vehicle.label,
      label: vehicle.label || "Autovehicul",
      plate: vehicle.plate || "",
      items,
      current,
      yearCost,
      warningCount: items.filter((item) => item && warningStatuses.has(item.status)).length + (items.length ? 0 : 1),
    };
  }

  _renderBatteryVehiclePanel(summary) {
    const open = this._batteryFormOpen.has(summary.key);
    const message = this._batteryMessage[summary.key] || "";
    return `
      <div class="cmr-cost-section">
        <div class="cmr-section-head">
          <div>
            <div class="cmr-section-title">${this._escape(summary.label)}</div>
            <div class="cmr-row-muted">${this._escape(summary.plate || "")}</div>
          </div>
          <button class="cmr-mini-action" type="button" data-action="toggle-battery-form" data-vehicle="${this._escape(summary.key)}">${open ? "Închide" : "Adaugă baterie"}</button>
        </div>
        <div class="cmr-cost-summary-grid cmr-fuel-summary-grid">
          ${this._renderCostSummaryCard("Baterie curentă", summary.current ? (summary.current.brand_model || summary.current.battery_type_label || "configurată") : "neconfigurată", summary.current ? (summary.current.status_label || "—") : "nu există baterie salvată")}
          ${this._renderCostSummaryCard("Vechime", summary.current && summary.current.age_years !== null && summary.current.age_years !== undefined ? `${summary.current.age_years} ani` : "—", summary.current?.install_date || "fără dată montare")}
          ${this._renderCostSummaryCard("Garanție", summary.current?.warranty_until || "—", summary.current?.warranty_days_remaining !== null && summary.current?.warranty_days_remaining !== undefined ? `${summary.current.warranty_days_remaining} zile` : "fără garanție")}
          ${this._renderCostSummaryCard("Cost an curent", summary.yearCost, "după data montării")}
        </div>
        ${open ? this._renderBatteryForm(summary.vehicle) : ""}
        ${message ? `<div class="cmr-message">${this._escape(message)}</div>` : ""}
        ${this._renderBatteryItems(summary)}
      </div>
    `;
  }

  _renderBatteryForm(vehicle) {
    const vehicleKey = vehicle.vehicle_id || vehicle.key || vehicle.label || "";
    const draft = this._batteryDrafts[vehicleKey] || {};
    return `
      <form class="cmr-history-form" data-form="battery-item" data-vehicle="${this._escape(vehicleKey)}" data-vehicle-ref="${this._escape(vehicle.vehicle_id || vehicle.plate || vehicle.label || vehicle.key || "")}">
        <div class="cmr-add-grid">
          <label class="cmr-field"><span>Marcă / model</span><input type="text" name="brand_model" value="${this._escape(draft.brand_model || "")}" placeholder="ex. Varta Silver Dynamic"></label>
          <label class="cmr-field"><span>Tip baterie</span><select name="battery_type">${this._batteryTypeOptions(draft.battery_type)}</select></label>
          <label class="cmr-field"><span>Capacitate Ah</span><input type="number" name="capacity_ah" min="0" step="1" value="${this._escape(draft.capacity_ah || "0")}"></label>
          <label class="cmr-field"><span>CCA / curent pornire</span><input type="number" name="cca" min="0" step="1" value="${this._escape(draft.cca || "0")}"></label>
          <label class="cmr-field"><span>Polaritate</span><input type="text" name="polarity" value="${this._escape(draft.polarity || "")}" placeholder="ex. dreapta +"></label>
          <label class="cmr-field"><span>Dimensiune</span><input type="text" name="size" value="${this._escape(draft.size || "")}" placeholder="ex. 278x175x190"></label>
          <label class="cmr-field"><span>Data montării</span><input type="date" name="install_date" value="${this._escape(this._formatDateInputValue(draft.install_date || ""))}"></label>
          <label class="cmr-field"><span>Km la montare</span><input type="number" name="install_km" min="0" step="1" value="${this._escape(draft.install_km || "0")}"></label>
          <label class="cmr-field"><span>Garanție până la</span><input type="date" name="warranty_until" value="${this._escape(this._formatDateInputValue(draft.warranty_until || ""))}"></label>
          <label class="cmr-field"><span>Cost</span><input type="number" name="cost" min="0" step="0.01" value="${this._escape(draft.cost || "0")}"></label>
        </div>
        <label class="cmr-check"><input type="checkbox" name="installed" ${draft.installed === false ? "" : "checked"}> Montată acum</label>
        <label class="cmr-field"><span>Observații</span><textarea name="notes" rows="2">${this._escape(draft.notes || "")}</textarea></label>
        <div class="cmr-add-actions"><button class="cmr-action" type="submit" ${this._batteryBusy === vehicleKey ? "disabled" : ""}>${this._batteryBusy === vehicleKey ? "Se salvează..." : "Salvează bateria"}</button></div>
      </form>
    `;
  }

  _renderBatteryItems(summary) {
    const items = Array.isArray(summary.items) ? summary.items : [];
    if (!items.length) return `<div class="cmr-history-empty">Nu există baterii salvate pentru acest autovehicul.</div>`;
    return `<div class="cmr-cost-list">${items.map((item) => this._renderBatteryItem(summary, item)).join("")}</div>`;
  }

  _renderBatteryItem(summary, item) {
    const batteryId = item.battery_id || "";
    const editOpen = batteryId && this._batteryEditOpen.has(batteryId);
    const title = [item.brand_model || "Baterie", item.battery_type_label || ""].filter(Boolean).join(" · ");
    const specs = [item.capacity_ah ? `${item.capacity_ah} Ah` : "", item.cca ? `${item.cca} CCA` : "", item.size || "", item.polarity || ""].filter(Boolean).join(" · ");
    const meta = [item.installed ? "montată acum" : "nemontată", item.install_date ? `montată ${this._formatDateForDisplay(item.install_date)}` : "fără dată montare", item.warranty_until ? `garanție ${this._formatDateForDisplay(item.warranty_until)}` : "fără garanție", item.status_label || ""].filter(Boolean).join(" · ");
    return `
      <div class="cmr-cost-item cmr-cost-item-block">
        <div class="cmr-cost-item-main">
          <div class="cmr-cost-item-title">${this._escape(title)} ${item.status === "warranty_expired" || item.status === "very_old" ? `<span>alertă</span>` : ""}</div>
          <div class="cmr-row-muted">${this._escape(specs || meta)}</div>
          <div class="cmr-row-muted">${this._escape(meta)}</div>
          ${item.notes ? `<div class="cmr-history-notes">${this._escape(item.notes)}</div>` : ""}
        </div>
        <div class="cmr-cost-item-side">
          <div class="cmr-cost-item-value">${this._formatMoney(item.cost)}</div>
          <div class="cmr-inline-actions">
            <button class="cmr-mini-action" type="button" data-action="toggle-edit-battery" data-battery-id="${this._escape(batteryId)}">${editOpen ? "Renunță" : "Editează"}</button>
            <button class="cmr-mini-action cmr-danger" type="button" data-action="delete-battery" data-battery-id="${this._escape(batteryId)}" data-vehicle="${this._escape(summary.key)}" data-battery-label="${this._escape(title)}">Șterge</button>
          </div>
        </div>
        ${editOpen ? this._renderBatteryEditForm(summary.vehicle, item) : ""}
      </div>`;
  }

  _renderBatteryEditForm(vehicle, item) {
    const vehicleKey = vehicle.vehicle_id || vehicle.key || vehicle.label || "";
    const batteryId = item.battery_id || "";
    const draft = this._batteryEditDrafts[batteryId] || {};
    const value = (key, fallback = "") => draft[key] ?? item[key] ?? fallback;
    const installed = Object.prototype.hasOwnProperty.call(draft, "installed") ? draft.installed : !!item.installed;
    return `
      <form class="cmr-history-form cmr-inline-edit-form" data-form="battery-item-edit" data-battery-id="${this._escape(batteryId)}" data-vehicle="${this._escape(vehicleKey)}" data-vehicle-ref="${this._escape(vehicle.vehicle_id || vehicle.plate || vehicle.label || vehicle.key || "")}">
        <div class="cmr-add-grid">
          <label class="cmr-field"><span>Marcă / model</span><input type="text" name="brand_model" value="${this._escape(value("brand_model"))}"></label>
          <label class="cmr-field"><span>Tip baterie</span><select name="battery_type">${this._batteryTypeOptions(value("battery_type", "lead_acid"))}</select></label>
          <label class="cmr-field"><span>Capacitate Ah</span><input type="number" name="capacity_ah" min="0" step="1" value="${this._escape(value("capacity_ah", "0"))}"></label>
          <label class="cmr-field"><span>CCA / curent pornire</span><input type="number" name="cca" min="0" step="1" value="${this._escape(value("cca", "0"))}"></label>
          <label class="cmr-field"><span>Polaritate</span><input type="text" name="polarity" value="${this._escape(value("polarity"))}"></label>
          <label class="cmr-field"><span>Dimensiune</span><input type="text" name="size" value="${this._escape(value("size"))}"></label>
          <label class="cmr-field"><span>Data montării</span><input type="date" name="install_date" value="${this._escape(this._formatDateInputValue(value("install_date")))}"></label>
          <label class="cmr-field"><span>Km la montare</span><input type="number" name="install_km" min="0" step="1" value="${this._escape(value("install_km", "0"))}"></label>
          <label class="cmr-field"><span>Garanție până la</span><input type="date" name="warranty_until" value="${this._escape(this._formatDateInputValue(value("warranty_until")))}"></label>
          <label class="cmr-field"><span>Cost</span><input type="number" name="cost" min="0" step="0.01" value="${this._escape(value("cost", "0"))}"></label>
        </div>
        <label class="cmr-check"><input type="checkbox" name="installed" ${installed ? "checked" : ""}> Montată acum</label>
        <label class="cmr-field"><span>Observații</span><textarea name="notes" rows="2">${this._escape(value("notes"))}</textarea></label>
        <div class="cmr-add-actions"><button class="cmr-action" type="submit" ${this._batteryBusy === batteryId ? "disabled" : ""}>${this._batteryBusy === batteryId ? "Se salvează..." : "Salvează modificările"}</button></div>
      </form>
    `;
  }

  _captureBatteryDraft(form) {
    if (!form) return;
    const vehicleKey = form.dataset.vehicle;
    const data = new FormData(form);
    this._batteryDrafts[vehicleKey] = this._batteryPayloadFromForm(data);
  }

  _captureBatteryEditDraft(form) {
    if (!form) return;
    const batteryId = form.dataset.batteryId;
    if (!batteryId) return;
    const data = new FormData(form);
    this._batteryEditDrafts[batteryId] = this._batteryPayloadFromForm(data);
  }

  _batteryPayloadFromForm(data) {
    return {
      installed: data.get("installed") === "on",
      brand_model: (data.get("brand_model") || "").toString(),
      battery_type: (data.get("battery_type") || "lead_acid").toString(),
      capacity_ah: (data.get("capacity_ah") || "0").toString(),
      cca: (data.get("cca") || "0").toString(),
      polarity: (data.get("polarity") || "").toString(),
      size: (data.get("size") || "").toString(),
      install_date: this._formDate(data, "install_date"),
      install_km: (data.get("install_km") || "0").toString(),
      warranty_until: this._formDate(data, "warranty_until"),
      cost: (data.get("cost") || "0").toString(),
      notes: (data.get("notes") || "").toString(),
    };
  }

  _validateBatteryPayload(payload) {
    if (!payload) return "Bateria nu conține date valide.";
    if (this._toNumber(payload.capacity_ah) < 0) return "Capacitatea nu poate fi negativă.";
    if (this._toNumber(payload.cca) < 0) return "Curentul de pornire nu poate fi negativ.";
    if (this._toNumber(payload.install_km) < 0) return "Kilometrajul nu poate fi negativ.";
    if (this._toNumber(payload.cost) < 0) return "Costul nu poate fi negativ.";
    return "";
  }

  _setBatteryMessage(vehicleKey, message) {
    if (!vehicleKey) return;
    this._batteryMessage[vehicleKey] = message;
    this.render();
  }

  _buildBatteryPayload(form, batteryId = null) {
    const data = new FormData(form);
    const payload = {
      vehicle_id: form.dataset.vehicleRef || form.dataset.vehicle,
      installed: data.get("installed") === "on",
      brand_model: (data.get("brand_model") || "").toString().trim(),
      battery_type: (data.get("battery_type") || "lead_acid").toString(),
      capacity_ah: Number(data.get("capacity_ah") || 0),
      cca: Number(data.get("cca") || 0),
      polarity: (data.get("polarity") || "").toString().trim(),
      size: (data.get("size") || "").toString().trim(),
      install_date: this._formDate(data, "install_date"),
      install_km: Number(data.get("install_km") || 0),
      warranty_until: this._formDate(data, "warranty_until"),
      cost: Number(data.get("cost") || 0),
      notes: (data.get("notes") || "").toString().trim(),
    };
    if (batteryId) payload.battery_id = batteryId;
    return payload;
  }

  async _addBattery(form) {
    if (!this._hass || !form || this._batteryBusy) return;
    const vehicleKey = form.dataset.vehicle;
    const payload = this._buildBatteryPayload(form);
    const error = this._validateBatteryPayload(payload);
    if (error) return this._setBatteryMessage(vehicleKey, error);
    this._batteryBusy = vehicleKey;
    this._batteryMessage[vehicleKey] = "";
    this.render();
    try {
      await this._hass.callService("car_manager_romania", "add_battery", payload);
      this._batteryMessage[vehicleKey] = "Bateria a fost salvată. Integrarea se reîncarcă pentru actualizare.";
      this._batteryDrafts[vehicleKey] = {};
      this._batteryFormOpen.delete(vehicleKey);
    } catch (error) {
      this._batteryMessage[vehicleKey] = error?.message || "Nu am putut salva bateria.";
    } finally {
      this._batteryBusy = null;
      this.render();
    }
  }

  async _updateBattery(form) {
    if (!this._hass || !form || this._batteryBusy) return;
    const batteryId = form.dataset.batteryId;
    const vehicleKey = form.dataset.vehicle;
    const payload = this._buildBatteryPayload(form, batteryId);
    const error = this._validateBatteryPayload(payload);
    if (error) return this._setBatteryMessage(vehicleKey, error);
    this._batteryBusy = batteryId;
    this._batteryMessage[vehicleKey] = "";
    this.render();
    try {
      await this._hass.callService("car_manager_romania", "update_battery", payload);
      this._batteryMessage[vehicleKey] = "Bateria a fost actualizată.";
      delete this._batteryEditDrafts[batteryId];
      this._batteryEditOpen.delete(batteryId);
    } catch (error) {
      this._batteryMessage[vehicleKey] = error?.message || "Nu am putut actualiza bateria.";
    } finally {
      this._batteryBusy = null;
      this.render();
    }
  }

  async _deleteBattery(batteryId, vehicleKey, label = "") {
    if (!this._hass || !batteryId || this._batteryBusy) return;
    const confirmed = window.confirm(`Ștergi definitiv această baterie?${label ? `\n\nBaterie: ${label}` : ""}\n\nOperațiunea nu poate fi anulată din card.`);
    if (!confirmed) return;
    this._batteryBusy = batteryId;
    this._batteryMessage[vehicleKey] = "";
    this.render();
    try {
      await this._hass.callService("car_manager_romania", "delete_battery", { battery_id: batteryId });
      this._batteryMessage[vehicleKey] = "Bateria a fost ștearsă.";
      delete this._batteryEditDrafts[batteryId];
      this._batteryEditOpen.delete(batteryId);
    } catch (error) {
      this._batteryMessage[vehicleKey] = error?.message || "Nu am putut șterge bateria.";
    } finally {
      this._batteryBusy = null;
      this.render();
    }
  }

  _renderEquipmentTab(vehicles) {
    if (!vehicles.length) return this._renderEmpty();

    const allSummaries = vehicles.map((vehicle) => this._equipmentSummaryForVehicle(vehicle));
    if (this._equipmentVehicleFilter !== "all" && !allSummaries.some((summary) => summary.key === this._equipmentVehicleFilter)) {
      this._equipmentVehicleFilter = "all";
    }
    const summaries = this._equipmentVehicleFilter === "all"
      ? allSummaries
      : allSummaries.filter((summary) => summary.key === this._equipmentVehicleFilter);
    const totalItems = summaries.reduce((sum, item) => sum + item.activeItems.length, 0);
    const presentItems = summaries.reduce((sum, item) => sum + item.presentItems.length, 0);
    const expiredItems = summaries.reduce((sum, item) => sum + item.expiredItems.length, 0);
    const soonItems = summaries.reduce((sum, item) => sum + item.soonItems.length, 0);
    const missingItems = summaries.reduce((sum, item) => sum + item.missingMandatory.length, 0);
    const totalAnnual = summaries.reduce((sum, item) => sum + item.yearCost, 0);
    return `
      <section class="cmr-costs-panel">
        <div class="cmr-section-head cmr-fuel-head">
          <div>
            <div class="cmr-section-title">Echipamente siguranță</div>
            <div class="cmr-row-muted">Trusă medicală, stingător, triunghiuri, vestă, kit pană și alte dotări</div>
          </div>
          <div class="cmr-fuel-head-actions">
            ${this._renderEquipmentVehicleFilter(allSummaries)}
          </div>
        </div>
        <div class="cmr-cost-summary-grid">
          ${this._renderCostSummaryCard("Echipamente", `${totalItems}`, this._equipmentVehicleFilter === "all" ? "Total elemente salvate" : "Elemente pentru mașina selectată")}
          ${this._renderCostSummaryCard("Prezente", `${presentItems}`, "Marcate ca existente în mașină")}
          ${this._renderCostSummaryCard("Alerte", `${expiredItems + soonItems + missingItems}`, missingItems ? `${missingItems} lipsă / neconfigurate` : (soonItems ? `${soonItems} expiră în 90 zile` : "fără alerte apropiate"))}
          ${this._renderCostSummaryCard("Cost an curent", totalAnnual, "După data cumpărării")}
        </div>
        ${summaries.map((summary) => this._renderEquipmentVehiclePanel(summary)).join("")}
      </section>
    `;
  }

  _renderEquipmentVehicleFilter(summaries) {
    if (!Array.isArray(summaries) || summaries.length <= 1) return "";
    return `
      <label class="cmr-fuel-filter">
        <span>Mașină</span>
        <select data-action="equipment-filter">
          <option value="all" ${this._equipmentVehicleFilter === "all" ? "selected" : ""}>Toate</option>
          ${summaries.map((summary) => `<option value="${this._escape(summary.key)}" ${this._equipmentVehicleFilter === summary.key ? "selected" : ""}>${this._escape(summary.label)}</option>`).join("")}
        </select>
      </label>
    `;
  }

  _mandatoryEquipmentTypes() {
    return [
      ["first_aid_kit", "Trusă medicală"],
      ["fire_extinguisher", "Stingător"],
      ["warning_triangles", "Triunghiuri reflectorizante"],
      ["reflective_vest", "Vestă reflectorizantă"],
    ];
  }

  _equipmentTypeLabel(type) {
    const found = this._equipmentTypeList().find(([value]) => value === type);
    return found ? found[1] : (type || "Echipament");
  }

  _equipmentTypeList() {
    return [
      ["first_aid_kit", "Trusă medicală"],
      ["fire_extinguisher", "Stingător"],
      ["warning_triangles", "Triunghiuri reflectorizante"],
      ["reflective_vest", "Vestă reflectorizantă"],
      ["spare_wheel", "Roată de rezervă"],
      ["puncture_kit", "Kit pană"],
      ["compressor", "Compresor"],
      ["jack", "Cric"],
      ["wheel_wrench", "Cheie roți"],
      ["jump_cables", "Cabluri pornire"],
      ["snow_chains", "Lanțuri antiderapante"],
      ["other", "Alt echipament"],
    ];
  }

  _equipmentSummaryForVehicle(vehicle) {
    const attrs = this._vehicleStatusAttributes(vehicle);
    const items = Array.isArray(attrs.equipment_items) ? attrs.equipment_items : [];
    const activeItems = items.filter((item) => item && !item.ignored);
    const ignoredItems = items.filter((item) => item && item.ignored);
    const ignoredTypes = new Set(ignoredItems.map((item) => item.equipment_type).filter(Boolean));
    const currentYear = new Date().getFullYear();
    const yearCost = activeItems.reduce((sum, item) => {
      const parts = this._dateParts(item.purchase_date);
      return sum + (parts && parts.year === currentYear ? this._toNumber(item.cost) : 0);
    }, 0);
    const expiredItems = activeItems.filter((item) => item && item.status === "expirat");
    const soonItems = activeItems.filter((item) => item && (item.status === "critic" || item.status === "în curând"));
    const missingMandatory = this._mandatoryEquipmentTypes()
      .filter(([type]) => !ignoredTypes.has(type) && !activeItems.some((item) => item.equipment_type === type))
      .map(([type, label]) => ({ equipment_type: type, equipment_type_label: label }));
    return {
      vehicle,
      key: vehicle.vehicle_id || vehicle.key || vehicle.label,
      label: vehicle.label || "Autovehicul",
      plate: vehicle.plate || "",
      items,
      activeItems,
      ignoredItems,
      missingMandatory,
      presentItems: activeItems.filter((item) => item && item.present),
      expiredItems,
      soonItems,
      yearCost,
    };
  }

  _renderEquipmentVehiclePanel(summary) {
    const open = this._equipmentFormOpen.has(summary.key);
    const message = this._equipmentMessage[summary.key] || "";
    return `
      <div class="cmr-cost-section">
        <div class="cmr-section-head">
          <div>
            <div class="cmr-section-title">${this._escape(summary.label)}</div>
            <div class="cmr-row-muted">${this._escape(summary.plate || "")}</div>
          </div>
          <button class="cmr-mini-action" type="button" data-action="toggle-equipment-form" data-vehicle="${this._escape(summary.key)}">${open ? "Închide" : "Adaugă"}</button>
        </div>
        <div class="cmr-cost-summary-grid cmr-fuel-summary-grid">
          ${this._renderCostSummaryCard("Elemente", `${summary.activeItems.length}`, `${summary.presentItems.length} prezente`)}
          ${this._renderCostSummaryCard("Alerte", `${summary.expiredItems.length + summary.soonItems.length + summary.missingMandatory.length}`, summary.missingMandatory.length ? `${summary.missingMandatory.length} lipsă / neconfigurate` : `${summary.expiredItems.length} expirate`)}
          ${this._renderCostSummaryCard("Cost an curent", summary.yearCost, "după data cumpărării")}
        </div>
        ${open ? this._renderEquipmentForm(summary.vehicle) : ""}
        ${message ? `<div class="cmr-message">${this._escape(message)}</div>` : ""}
        ${this._renderEquipmentItems(summary)}
      </div>
    `;
  }

  _equipmentTypeOptions(selected) {
    const selectedValue = selected || "first_aid_kit";
    return this._equipmentTypeList().map(([value, label]) => `<option value="${value}" ${value === selectedValue ? "selected" : ""}>${label}</option>`).join("");
  }

  _renderEquipmentForm(vehicle) {
    const vehicleKey = vehicle.vehicle_id || vehicle.key || vehicle.label || "";
    const draft = this._equipmentDrafts[vehicleKey] || {};
    return `
      <form class="cmr-history-form" data-form="equipment-item" data-vehicle="${this._escape(vehicleKey)}" data-vehicle-ref="${this._escape(vehicle.vehicle_id || vehicle.plate || vehicle.label || vehicle.key || "")}">
        <div class="cmr-add-grid">
          <label class="cmr-field"><span>Tip echipament</span><select name="equipment_type">${this._equipmentTypeOptions(draft.equipment_type)}</select></label>
          <label class="cmr-field"><span>Denumire / model</span><input type="text" name="name" value="${this._escape(draft.name || "")}" placeholder="ex. Trusă auto omologată"></label>
          <label class="cmr-field"><span>Data cumpărării</span><input type="date" name="purchase_date" value="${this._escape(this._formatDateInputValue(draft.purchase_date || ""))}"></label>
          <label class="cmr-field"><span>Expiră la</span><input type="date" name="expiry_date" value="${this._escape(this._formatDateInputValue(draft.expiry_date || ""))}"></label>
          <label class="cmr-field"><span>Cost</span><input type="number" name="cost" min="0" step="0.01" value="${this._escape(draft.cost || "0")}"></label>
          <label class="cmr-field"><span>Loc depozitare</span><input type="text" name="storage_location" value="${this._escape(draft.storage_location || "")}" placeholder="ex. portbagaj"></label>
        </div>
        <label class="cmr-check"><input type="checkbox" name="present" ${draft.present === false ? "" : "checked"}> Există în mașină</label>
        <label class="cmr-field"><span>Observații</span><textarea name="notes" rows="2">${this._escape(draft.notes || "")}</textarea></label>
        <div class="cmr-add-actions"><button class="cmr-action" type="submit" ${this._equipmentBusy === vehicleKey ? "disabled" : ""}>${this._equipmentBusy === vehicleKey ? "Se salvează..." : "Salvează echipamentul"}</button></div>
      </form>
    `;
  }

  _renderEquipmentItems(summary) {
    const activeItems = Array.isArray(summary.activeItems) ? summary.activeItems : [];
    const ignoredItems = Array.isArray(summary.ignoredItems) ? summary.ignoredItems : [];
    const missingMandatory = Array.isArray(summary.missingMandatory) ? summary.missingMandatory : [];
    const parts = [];
    if (missingMandatory.length) {
      parts.push(`<div class="cmr-equipment-missing">
        <div class="cmr-row-muted">Echipamente obligatorii lipsă / neconfigurate</div>
        ${missingMandatory.map((item) => this._renderMissingEquipmentItem(summary, item)).join("")}
      </div>`);
    }
    if (activeItems.length) {
      parts.push(`<div class="cmr-cost-list">${activeItems.map((item) => this._renderEquipmentItem(summary, item)).join("")}</div>`);
    }
    if (ignoredItems.length) {
      parts.push(`<div class="cmr-equipment-missing">
        <div class="cmr-row-muted">Echipamente neafișate la alerte</div>
        ${ignoredItems.map((item) => this._renderIgnoredEquipmentItem(summary, item)).join("")}
      </div>`);
    }
    if (!parts.length) return `<div class="cmr-history-empty">Nu există echipamente salvate pentru acest autovehicul.</div>`;
    return parts.join("");
  }

  _renderMissingEquipmentItem(summary, item) {
    const type = item.equipment_type || "";
    const label = item.equipment_type_label || this._equipmentTypeLabel(type);
    return `
      <div class="cmr-equipment-required-card">
        <div class="cmr-equipment-required-head">
          <strong>${this._escape(label)}</strong>
          <span>neconfigurat</span>
        </div>
        <div class="cmr-equipment-required-note">Element recomandat pentru siguranță. Adaugă-l sau ascunde-l dacă nu vrei să îl urmărești.</div>
        <div class="cmr-equipment-required-actions">
          <button class="cmr-mini-action" type="button" data-action="prepare-missing-equipment" data-vehicle="${this._escape(summary.key)}" data-equipment-type="${this._escape(type)}">Adaugă</button>
          <button class="cmr-mini-action cmr-danger" type="button" data-action="ignore-equipment-type" data-vehicle="${this._escape(summary.key)}" data-vehicle-ref="${this._escape(summary.vehicle.vehicle_id || summary.vehicle.plate || summary.vehicle.label || summary.vehicle.key || "")}" data-equipment-type="${this._escape(type)}" data-equipment-label="${this._escape(label)}">Nu urmăresc</button>
        </div>
      </div>`;
  }

  _renderIgnoredEquipmentItem(summary, item) {
    const itemId = item.item_id || "";
    const label = item.equipment_type_label || "Echipament";
    return `
      <div class="cmr-equipment-required-card cmr-equipment-ignored-card">
        <div class="cmr-equipment-required-head">
          <strong>${this._escape(label)}</strong>
          <span>ignorat</span>
        </div>
        <div class="cmr-equipment-required-note">Nu apare în alerte și nu este inclus în costuri.</div>
        <div class="cmr-equipment-required-actions">
          <button class="cmr-mini-action" type="button" data-action="reactivate-equipment-type" data-item-id="${this._escape(itemId)}" data-vehicle="${this._escape(summary.key)}" data-equipment-label="${this._escape(label)}">Reactivează</button>
        </div>
      </div>`;
  }

  _renderEquipmentItem(summary, item) {
    const itemId = item.item_id || "";
    const editOpen = itemId && this._equipmentEditOpen.has(itemId);
    const title = [item.equipment_type_label || "Echipament", item.name || ""].filter(Boolean).join(" · ");
    const expiry = item.expiry_date ? `expiră ${this._formatDateForDisplay(item.expiry_date)}` : "fără expirare";
    const status = item.status || "—";
    const meta = [expiry, status, item.present ? "prezent" : "lipsă", item.storage_location || ""].filter(Boolean).join(" · ");
    return `
      <div class="cmr-cost-item cmr-cost-item-block">
        <div class="cmr-cost-item-main">
          <div class="cmr-cost-item-title">${this._escape(title || "Echipament")} ${status === "expirat" ? `<span>expirat</span>` : ""}</div>
          <div class="cmr-row-muted">${this._escape(meta)}</div>
          ${item.notes ? `<div class="cmr-history-notes">${this._escape(item.notes)}</div>` : ""}
        </div>
        <div class="cmr-cost-item-side">
          <div class="cmr-cost-item-value">${this._formatMoney(item.cost)}</div>
          <div class="cmr-inline-actions">
            <button class="cmr-mini-action" type="button" data-action="toggle-edit-equipment-item" data-item-id="${this._escape(itemId)}">${editOpen ? "Renunță" : "Editează"}</button>
            <button class="cmr-mini-action cmr-danger" type="button" data-action="delete-equipment-item" data-item-id="${this._escape(itemId)}" data-vehicle="${this._escape(summary.key)}" data-equipment-label="${this._escape(title)}">Șterge</button>
          </div>
        </div>
        ${editOpen ? this._renderEquipmentEditForm(summary.vehicle, item) : ""}
      </div>`;
  }

  _renderEquipmentEditForm(vehicle, item) {
    const vehicleKey = vehicle.vehicle_id || vehicle.key || vehicle.label || "";
    const itemId = item.item_id || "";
    const draft = this._equipmentEditDrafts[itemId] || {};
    const value = (key, fallback = "") => draft[key] ?? item[key] ?? fallback;
    const present = Object.prototype.hasOwnProperty.call(draft, "present") ? draft.present : !!item.present;
    return `
      <form class="cmr-history-form cmr-inline-edit-form" data-form="equipment-item-edit" data-item-id="${this._escape(itemId)}" data-vehicle="${this._escape(vehicleKey)}" data-vehicle-ref="${this._escape(vehicle.vehicle_id || vehicle.plate || vehicle.label || vehicle.key || "")}">
        <div class="cmr-add-grid">
          <label class="cmr-field"><span>Tip echipament</span><select name="equipment_type">${this._equipmentTypeOptions(value("equipment_type", "first_aid_kit"))}</select></label>
          <label class="cmr-field"><span>Denumire / model</span><input type="text" name="name" value="${this._escape(value("name"))}"></label>
          <label class="cmr-field"><span>Data cumpărării</span><input type="date" name="purchase_date" value="${this._escape(this._formatDateInputValue(value("purchase_date")))}"></label>
          <label class="cmr-field"><span>Expiră la</span><input type="date" name="expiry_date" value="${this._escape(this._formatDateInputValue(value("expiry_date")))}"></label>
          <label class="cmr-field"><span>Cost</span><input type="number" name="cost" min="0" step="0.01" value="${this._escape(value("cost", "0"))}"></label>
          <label class="cmr-field"><span>Loc depozitare</span><input type="text" name="storage_location" value="${this._escape(value("storage_location"))}"></label>
        </div>
        <label class="cmr-check"><input type="checkbox" name="present" ${present ? "checked" : ""}> Există în mașină</label>
        <label class="cmr-field"><span>Observații</span><textarea name="notes" rows="2">${this._escape(value("notes"))}</textarea></label>
        <div class="cmr-add-actions"><button class="cmr-action" type="submit" ${this._equipmentBusy === itemId ? "disabled" : ""}>${this._equipmentBusy === itemId ? "Se salvează..." : "Salvează modificările"}</button></div>
      </form>
    `;
  }

  _captureTireSetDraft(form) {
    if (!form) return;
    const vehicleKey = form.dataset.vehicle;
    const data = new FormData(form);
    this._tireSetDrafts[vehicleKey] = this._tirePayloadFromForm(data);
  }

  _captureTireSetEditDraft(form) {
    if (!form) return;
    const setId = form.dataset.setId;
    if (!setId) return;
    const data = new FormData(form);
    this._tireSetEditDrafts[setId] = this._tirePayloadFromForm(data);
  }

  _tirePayloadFromForm(data) {
    return {
      tire_type: (data.get("tire_type") || "summer").toString(),
      wheel_mount_type: (data.get("wheel_mount_type") || "tires_only").toString(),
      brand_model: (data.get("brand_model") || "").toString(),
      size: (data.get("size") || "").toString(),
      dot: (data.get("dot") || "").toString(),
      quantity: (data.get("quantity") || "4").toString(),
      purchase_date: this._formDate(data, "purchase_date"),
      last_mount_date: this._formDate(data, "last_mount_date"),
      last_mount_km: (data.get("last_mount_km") || "0").toString(),
      total_km: (data.get("total_km") || "0").toString(),
      cost: (data.get("cost") || "0").toString(),
      installed: data.get("installed") === "on",
      storage_location: (data.get("storage_location") || "").toString(),
      pressure_front: (data.get("pressure_front") || "").toString(),
      pressure_rear: (data.get("pressure_rear") || "").toString(),
      notes: (data.get("notes") || "").toString(),
    };
  }

  _validateTireSetPayload(payload) {
    if (!payload) return "Setul de anvelope nu conține date valide.";
    if (!payload.tire_type) return "Selectează tipul anvelopelor.";
    if (!Number.isFinite(payload.quantity) || payload.quantity <= 0) return "Numărul de bucăți trebuie să fie mai mare decât 0.";
    if (!Number.isFinite(payload.cost) || payload.cost < 0) return "Costul nu poate fi negativ.";
    if (!Number.isFinite(payload.last_mount_km) || payload.last_mount_km < 0) return "Km la montare nu poate fi negativ.";
    if (!Number.isFinite(payload.total_km) || payload.total_km < 0) return "Km parcurși cu setul nu poate fi negativ.";
    return "";
  }

  _setTireMessage(vehicleKey, message) {
    if (!vehicleKey) return;
    this._tireSetMessage[vehicleKey] = message;
    this.render();
  }

  _buildTirePayload(form, setId = null) {
    const data = new FormData(form);
    const payload = {
      vehicle_id: form.dataset.vehicleRef || form.dataset.vehicle,
      tire_type: (data.get("tire_type") || "summer").toString(),
      wheel_mount_type: (data.get("wheel_mount_type") || "tires_only").toString(),
      brand_model: (data.get("brand_model") || "").toString().trim(),
      size: (data.get("size") || "").toString().trim(),
      dot: (data.get("dot") || "").toString().trim(),
      quantity: Math.round(Number(data.get("quantity") || 4)),
      purchase_date: this._formDate(data, "purchase_date"),
      last_mount_date: this._formDate(data, "last_mount_date"),
      last_mount_km: Math.round(Number(data.get("last_mount_km") || 0)),
      total_km: Math.round(Number(data.get("total_km") || 0)),
      cost: Number(data.get("cost") || 0),
      installed: data.get("installed") === "on",
      storage_location: (data.get("storage_location") || "").toString().trim(),
      pressure_front: (data.get("pressure_front") || "").toString().trim(),
      pressure_rear: (data.get("pressure_rear") || "").toString().trim(),
      notes: (data.get("notes") || "").toString().trim(),
    };
    if (setId) payload.set_id = setId;
    return payload;
  }

  async _addTireSet(form) {
    if (!this._hass || !form || this._tireSetBusy) return;
    const vehicleKey = form.dataset.vehicle;
    const payload = this._buildTirePayload(form);
    const error = this._validateTireSetPayload(payload);
    if (error) return this._setTireMessage(vehicleKey, error);
    this._tireSetBusy = vehicleKey;
    this._tireSetMessage[vehicleKey] = "";
    this.render();
    try {
      await this._hass.callService("car_manager_romania", "add_tire_set", payload);
      this._tireSetMessage[vehicleKey] = "Setul de anvelope a fost salvat. Integrarea se reîncarcă pentru actualizare.";
      this._tireSetDrafts[vehicleKey] = {};
      this._tireFormOpen.delete(vehicleKey);
    } catch (error) {
      this._tireSetMessage[vehicleKey] = error?.message || "Nu am putut salva setul de anvelope.";
    } finally {
      this._tireSetBusy = null;
      this.render();
    }
  }

  async _updateTireSet(form) {
    if (!this._hass || !form || this._tireSetBusy) return;
    const setId = form.dataset.setId;
    const vehicleKey = form.dataset.vehicle;
    const payload = this._buildTirePayload(form, setId);
    const error = this._validateTireSetPayload(payload);
    if (error) return this._setTireMessage(vehicleKey, error);
    this._tireSetBusy = setId;
    this._tireSetMessage[vehicleKey] = "";
    this.render();
    try {
      await this._hass.callService("car_manager_romania", "update_tire_set", payload);
      this._tireSetMessage[vehicleKey] = "Setul de anvelope a fost actualizat.";
      delete this._tireSetEditDrafts[setId];
      this._tireSetEditOpen.delete(setId);
    } catch (error) {
      this._tireSetMessage[vehicleKey] = error?.message || "Nu am putut actualiza setul de anvelope.";
    } finally {
      this._tireSetBusy = null;
      this.render();
    }
  }

  async _deleteTireSet(setId, vehicleKey, label = "") {
    if (!this._hass || !setId || this._tireSetBusy) return;
    const confirmed = window.confirm(`Ștergi definitiv acest set de anvelope?${label ? `\n\nSet: ${label}` : ""}\n\nOperațiunea nu poate fi anulată din card.`);
    if (!confirmed) return;
    this._tireSetBusy = setId;
    this._tireSetMessage[vehicleKey] = "";
    this.render();
    try {
      await this._hass.callService("car_manager_romania", "delete_tire_set", { set_id: setId });
      this._tireSetMessage[vehicleKey] = "Setul de anvelope a fost șters.";
      delete this._tireSetEditDrafts[setId];
      this._tireSetEditOpen.delete(setId);
    } catch (error) {
      this._tireSetMessage[vehicleKey] = error?.message || "Nu am putut șterge setul de anvelope.";
    } finally {
      this._tireSetBusy = null;
      this.render();
    }
  }

  _prepareMissingEquipment(vehicleKey, equipmentType) {
    if (!vehicleKey || !equipmentType) return;
    this._equipmentDrafts[vehicleKey] = {
      ...(this._equipmentDrafts[vehicleKey] || {}),
      equipment_type: equipmentType,
      present: true,
      ignored: false,
    };
    this._equipmentFormOpen.add(vehicleKey);
    this.render();
  }

  async _ignoreEquipmentType(vehicleKey, vehicleRef, equipmentType, label = "") {
    if (!this._hass || !vehicleKey || !equipmentType || this._equipmentBusy) return;
    const confirmed = window.confirm(`Nu mai urmărești acest echipament pentru mașina selectată?${label ? `\n\nEchipament: ${label}` : ""}\n\nÎl vei putea reactiva din lista echipamentelor ignorate.`);
    if (!confirmed) return;
    this._equipmentBusy = `${vehicleKey}:${equipmentType}:ignore`;
    this._equipmentMessage[vehicleKey] = "";
    this.render();
    try {
      await this._hass.callService("car_manager_romania", "add_equipment_item", {
        vehicle_id: vehicleRef || vehicleKey,
        equipment_type: equipmentType,
        name: "Nu urmăresc",
        purchase_date: "",
        expiry_date: "",
        cost: 0,
        present: false,
        ignored: true,
        storage_location: "",
        notes: "Echipament ascuns din alerte din card.",
      });
      this._equipmentMessage[vehicleKey] = "Echipamentul a fost ascuns din alerte.";
    } catch (error) {
      this._equipmentMessage[vehicleKey] = error?.message || "Nu am putut ascunde echipamentul.";
    } finally {
      this._equipmentBusy = null;
      this.render();
    }
  }

  async _reactivateEquipmentType(itemId, vehicleKey, label = "") {
    if (!this._hass || !itemId || this._equipmentBusy) return;
    const confirmed = window.confirm(`Reactivezi urmărirea acestui echipament?${label ? `\n\nEchipament: ${label}` : ""}`);
    if (!confirmed) return;
    this._equipmentBusy = itemId;
    this._equipmentMessage[vehicleKey] = "";
    this.render();
    try {
      await this._hass.callService("car_manager_romania", "delete_equipment_item", { item_id: itemId });
      this._equipmentMessage[vehicleKey] = "Echipamentul a fost reactivat. Dacă nu este introdus, va apărea ca neconfigurat.";
    } catch (error) {
      this._equipmentMessage[vehicleKey] = error?.message || "Nu am putut reactiva echipamentul.";
    } finally {
      this._equipmentBusy = null;
      this.render();
    }
  }

  _captureEquipmentDraft(form) {
    if (!form) return;
    const vehicleKey = form.dataset.vehicle;
    const data = new FormData(form);
    this._equipmentDrafts[vehicleKey] = this._equipmentPayloadFromForm(data);
  }

  _captureEquipmentEditDraft(form) {
    if (!form) return;
    const itemId = form.dataset.itemId;
    if (!itemId) return;
    const data = new FormData(form);
    this._equipmentEditDrafts[itemId] = this._equipmentPayloadFromForm(data);
  }

  _equipmentPayloadFromForm(data) {
    return {
      equipment_type: (data.get("equipment_type") || "first_aid_kit").toString(),
      name: (data.get("name") || "").toString(),
      purchase_date: this._formDate(data, "purchase_date"),
      expiry_date: this._formDate(data, "expiry_date"),
      cost: (data.get("cost") || "0").toString(),
      present: data.get("present") === "on",
      ignored: false,
      storage_location: (data.get("storage_location") || "").toString(),
      notes: (data.get("notes") || "").toString(),
    };
  }

  _validateEquipmentPayload(payload) {
    if (!payload) return "Echipamentul nu conține date valide.";
    if (!payload.equipment_type) return "Selectează tipul echipamentului.";
    if (!Number.isFinite(payload.cost) || payload.cost < 0) return "Costul nu poate fi negativ.";
    return "";
  }

  _setEquipmentMessage(vehicleKey, message) {
    if (!vehicleKey) return;
    this._equipmentMessage[vehicleKey] = message;
    this.render();
  }

  _buildEquipmentPayload(form, itemId = null) {
    const data = new FormData(form);
    const payload = {
      vehicle_id: form.dataset.vehicleRef || form.dataset.vehicle,
      equipment_type: (data.get("equipment_type") || "first_aid_kit").toString(),
      name: (data.get("name") || "").toString().trim(),
      purchase_date: this._formDate(data, "purchase_date"),
      expiry_date: this._formDate(data, "expiry_date"),
      cost: Number(data.get("cost") || 0),
      present: data.get("present") === "on",
      ignored: false,
      storage_location: (data.get("storage_location") || "").toString().trim(),
      notes: (data.get("notes") || "").toString().trim(),
    };
    if (itemId) payload.item_id = itemId;
    return payload;
  }

  async _addEquipmentItem(form) {
    if (!this._hass || !form || this._equipmentBusy) return;
    const vehicleKey = form.dataset.vehicle;
    const payload = this._buildEquipmentPayload(form);
    const error = this._validateEquipmentPayload(payload);
    if (error) return this._setEquipmentMessage(vehicleKey, error);
    this._equipmentBusy = vehicleKey;
    this._equipmentMessage[vehicleKey] = "";
    this.render();
    try {
      await this._hass.callService("car_manager_romania", "add_equipment_item", payload);
      this._equipmentMessage[vehicleKey] = "Echipamentul a fost salvat. Integrarea se reîncarcă pentru actualizare.";
      this._equipmentDrafts[vehicleKey] = {};
      this._equipmentFormOpen.delete(vehicleKey);
    } catch (error) {
      this._equipmentMessage[vehicleKey] = error?.message || "Nu am putut salva echipamentul.";
    } finally {
      this._equipmentBusy = null;
      this.render();
    }
  }

  async _updateEquipmentItem(form) {
    if (!this._hass || !form || this._equipmentBusy) return;
    const itemId = form.dataset.itemId;
    const vehicleKey = form.dataset.vehicle;
    const payload = this._buildEquipmentPayload(form, itemId);
    const error = this._validateEquipmentPayload(payload);
    if (error) return this._setEquipmentMessage(vehicleKey, error);
    this._equipmentBusy = itemId;
    this._equipmentMessage[vehicleKey] = "";
    this.render();
    try {
      await this._hass.callService("car_manager_romania", "update_equipment_item", payload);
      this._equipmentMessage[vehicleKey] = "Echipamentul a fost actualizat.";
      delete this._equipmentEditDrafts[itemId];
      this._equipmentEditOpen.delete(itemId);
    } catch (error) {
      this._equipmentMessage[vehicleKey] = error?.message || "Nu am putut actualiza echipamentul.";
    } finally {
      this._equipmentBusy = null;
      this.render();
    }
  }

  async _deleteEquipmentItem(itemId, vehicleKey, label = "") {
    if (!this._hass || !itemId || this._equipmentBusy) return;
    const confirmed = window.confirm(`Ștergi definitiv acest echipament?${label ? `\n\nEchipament: ${label}` : ""}\n\nOperațiunea nu poate fi anulată din card.`);
    if (!confirmed) return;
    this._equipmentBusy = itemId;
    this._equipmentMessage[vehicleKey] = "";
    this.render();
    try {
      await this._hass.callService("car_manager_romania", "delete_equipment_item", { item_id: itemId });
      this._equipmentMessage[vehicleKey] = "Echipamentul a fost șters.";
      delete this._equipmentEditDrafts[itemId];
      this._equipmentEditOpen.delete(itemId);
    } catch (error) {
      this._equipmentMessage[vehicleKey] = error?.message || "Nu am putut șterge echipamentul.";
    } finally {
      this._equipmentBusy = null;
      this.render();
    }
  }

  _captureFuelReceiptDraft(form) {
    if (!form) return;
    const vehicleKey = form.dataset.vehicle;
    const data = new FormData(form);
    this._fuelReceiptDrafts[vehicleKey] = {
      date: this._formDate(data, "date"),
      km: (data.get("km") || "").toString(),
      fuel_type: (data.get("fuel_type") || "").toString(),
      quantity: (data.get("quantity") || "").toString(),
      total_cost: (data.get("total_cost") || "").toString(),
      full_tank: data.get("full_tank") === "on",
      station: (data.get("station") || "").toString(),
      notes: (data.get("notes") || "").toString(),
    };
  }

  _captureFuelReceiptEditDraft(form) {
    if (!form) return;
    const receiptId = form.dataset.receiptId;
    if (!receiptId) return;
    const data = new FormData(form);
    this._fuelReceiptEditDrafts[receiptId] = {
      date: this._formDate(data, "date"),
      km: (data.get("km") || "").toString(),
      fuel_type: (data.get("fuel_type") || "").toString(),
      quantity: (data.get("quantity") || "").toString(),
      total_cost: (data.get("total_cost") || "").toString(),
      full_tank: data.get("full_tank") === "on",
      station: (data.get("station") || "").toString(),
      notes: (data.get("notes") || "").toString(),
    };
  }

  _validateFuelReceiptPayload(payload) {
    if (!payload) return "Bonul nu conține date valide.";
    if (!payload.date || !/^\d{4}-\d{2}-\d{2}$/.test(String(payload.date))) return "Completează data alimentării.";
    if (!payload.fuel_type) return "Selectează tipul de combustibil.";
    if (!Number.isFinite(payload.km) || payload.km <= 0) return "Kilometrajul din bord trebuie să fie mai mare decât 0.";
    if (!Number.isFinite(payload.quantity) || payload.quantity <= 0) return "Cantitatea alimentată trebuie să fie mai mare decât 0.";
    if (!Number.isFinite(payload.total_cost) || payload.total_cost <= 0) return "Valoarea bonului trebuie să fie mai mare decât 0.";
    return "";
  }

  _setFuelMessage(vehicleKey, message) {
    if (!vehicleKey) return;
    this._fuelReceiptMessage[vehicleKey] = message;
    this.render();
  }

  _exportFuelHistory() {
    const summaries = this._buildVehicles().map((vehicle) => this._fuelSummaryForVehicle(vehicle));
    const filtered = this._fuelVehicleFilter === "all"
      ? summaries
      : summaries.filter((summary) => summary.key === this._fuelVehicleFilter);
    const payload = {
      type: "car_manager_romania_fuel_history",
      version: "1.0.16",
      generated_at: new Date().toISOString(),
      filter: this._fuelVehicleFilter,
      vehicles: filtered.map((summary) => ({
        vehicle_id: summary.key,
        label: summary.label,
        plate: summary.plate,
        year_cost: summary.yearCost,
        month_cost: summary.monthCost,
        receipts: Array.isArray(summary.receipts) ? summary.receipts : [],
        consumption_intervals: Array.isArray(summary.intervals) ? summary.intervals : [],
      })),
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const suffix = this._fuelVehicleFilter === "all" ? "toate" : this._fuelVehicleFilter;
    a.href = url;
    a.download = `car_manager_romania_combustibil_${suffix}_${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  _confirmFuelKmIfNeeded(vehicleKey, km, currentReceiptId = null) {
    const currentKm = Number(km || 0);
    if (!vehicleKey || !Number.isFinite(currentKm) || currentKm <= 0) return true;
    const vehicle = this._buildVehicles().find((item) => (item.vehicle_id || item.key || item.label) === vehicleKey);
    if (!vehicle) return true;
    const receipts = Array.isArray(this._vehicleStatusAttributes(vehicle).fuel_receipts)
      ? this._vehicleStatusAttributes(vehicle).fuel_receipts
      : [];
    const comparable = receipts
      .filter((receipt) => receipt && typeof receipt === "object" && (!currentReceiptId || receipt.receipt_id !== currentReceiptId))
      .map((receipt) => this._toNumber(receipt.km))
      .filter((value) => value > 0);
    if (!comparable.length) return true;
    const maxKm = Math.max(...comparable);
    if (currentKm >= maxKm) return true;
    return window.confirm(`Kilometrajul introdus (${currentKm} km) este mai mic decât cel mai mare kilometraj salvat pentru această mașină (${maxKm} km). Salvez totuși bonul?`);
  }

  async _addFuelReceipt(form) {
    if (!this._hass || !form) return;
    const vehicleKey = form.dataset.vehicle;
    if (this._fuelReceiptBusy) return;
    const data = new FormData(form);
    const payload = {
      vehicle_id: form.dataset.vehicleRef || vehicleKey,
      date: this._formDate(data, "date"),
      km: Math.round(Number(data.get("km") || 0)),
      fuel_type: (data.get("fuel_type") || "").toString(),
      quantity: Number(data.get("quantity") || 0),
      total_cost: Number(data.get("total_cost") || 0),
      full_tank: data.get("full_tank") === "on",
      station: (data.get("station") || "").toString().trim(),
      notes: (data.get("notes") || "").toString().trim(),
    };
    const validationError = this._validateFuelReceiptPayload(payload);
    if (validationError) {
      this._setFuelMessage(vehicleKey, validationError);
      return;
    }
    if (!this._confirmFuelKmIfNeeded(vehicleKey, payload.km)) return;
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

  async _updateFuelReceipt(form) {
    if (!this._hass || !form) return;
    const receiptId = form.dataset.receiptId;
    const vehicleKey = form.dataset.vehicle;
    if (!receiptId || this._fuelReceiptBusy) return;
    const data = new FormData(form);
    const payload = {
      receipt_id: receiptId,
      vehicle_id: form.dataset.vehicleRef || vehicleKey,
      date: this._formDate(data, "date"),
      km: Math.round(Number(data.get("km") || 0)),
      fuel_type: (data.get("fuel_type") || "").toString(),
      quantity: Number(data.get("quantity") || 0),
      total_cost: Number(data.get("total_cost") || 0),
      full_tank: data.get("full_tank") === "on",
      station: (data.get("station") || "").toString().trim(),
      notes: (data.get("notes") || "").toString().trim(),
    };
    const validationError = this._validateFuelReceiptPayload(payload);
    if (validationError) {
      this._setFuelMessage(vehicleKey, validationError);
      return;
    }
    if (!this._confirmFuelKmIfNeeded(vehicleKey, payload.km, receiptId)) return;
    this._fuelReceiptBusy = receiptId;
    this._fuelReceiptMessage[vehicleKey] = "";
    this.render();
    try {
      await this._hass.callService("car_manager_romania", "update_fuel_receipt", payload);
      this._fuelReceiptMessage[vehicleKey] = "Bonul a fost actualizat. Integrarea se reîncarcă pentru recalcularea consumului.";
      delete this._fuelReceiptEditDrafts[receiptId];
      this._fuelReceiptEditOpen.delete(receiptId);
    } catch (error) {
      this._fuelReceiptMessage[vehicleKey] = error?.message || "Nu am putut actualiza bonul.";
    } finally {
      this._fuelReceiptBusy = null;
      this.render();
    }
  }

  async _deleteFuelReceipt(receiptId, vehicleKey, receiptLabel = "") {
    if (!this._hass || !receiptId || this._fuelReceiptBusy) return;
    const detail = receiptLabel ? `\n\nBon: ${receiptLabel}` : "";
    const confirmed = window.confirm(`Ștergi definitiv acest bon de combustibil?${detail}\n\nDupă ștergere se recalculează costurile, prețul mediu și consumul. Operațiunea nu poate fi anulată din card.`);
    if (!confirmed) return;
    this._fuelReceiptBusy = receiptId;
    this._fuelReceiptMessage[vehicleKey] = "";
    this.render();
    try {
      await this._hass.callService("car_manager_romania", "delete_fuel_receipt", { receipt_id: receiptId });
      this._fuelReceiptMessage[vehicleKey] = "Bonul a fost șters. Integrarea se reîncarcă pentru recalcularea consumului.";
      delete this._fuelReceiptEditDrafts[receiptId];
      this._fuelReceiptEditOpen.delete(receiptId);
    } catch (error) {
      this._fuelReceiptMessage[vehicleKey] = error?.message || "Nu am putut șterge bonul.";
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
      date: this._formDate(data, "date"),
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

    const title = options.title ? `\n\nIntervenție: ${options.title}` : "";
    const warning = options.updatesMaintenance && !options.restored
      ? `Ștergi definitiv această intervenție din istoric?${title}\n\nAtenție: intervenția pare aplicată în mentenanță. Ștergerea elimină doar rândul din istoric, nu revine la valorile anterioare. Pentru revenire, folosește mai întâi Restore, apoi Șterge.`
      : `Ștergi definitiv această intervenție din istoric?${title}\n\nValorile de mentenanță ale autovehiculului nu se modifică. Operațiunea nu poate fi anulată din card.`;
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
      this._hass.callService("date", "set_value", { date: this._parseDateInputValue(value) || null }, { entity_id: entityId });
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
    const rovStatus = this._findRovinietaStatus(vehicle);
    const rovDays = this._findRovinietaDays(vehicle);
    const rovExpiry = this._findRovinietaExpiry(vehicle);

    return {
      km: this._entityValue(km),
      serviceStatus: this._entityValue(serviceStatus),
      serviceDays: this._formatDays(this._entityValue(serviceDays)),
      serviceKm: this._formatKm(this._entityValue(serviceKm)),
      rcaStatus: this._entityValue(rcaStatus),
      rcaDays: this._formatDays(this._entityValue(rcaDays)),
      rcaExpiry: this._formatDateForDisplay(this._entityValue(rcaExpiry)),
      cascoStatus: this._entityValue(cascoStatus),
      cascoDays: this._formatDays(this._entityValue(cascoDays)),
      cascoExpiry: this._formatDateForDisplay(this._entityValue(cascoExpiry)),
      itpStatus: this._entityValue(itpStatus),
      itpDays: this._formatDays(this._entityValue(itpDays)),
      itpExpiry: this._formatDateForDisplay(this._entityValue(itpExpiry)),
      rovinietaStatus: this._entityValue(rovStatus),
      rovinietaDays: this._formatDays(this._entityValue(rovDays)),
      rovinietaExpiry: this._formatDateForDisplay(this._entityValue(rovExpiry)),
    };
  }


  _findSensorByName(vehicle, terms, excludeTerms = []) {
    const found = this._findByName(vehicle, terms, excludeTerms, (entity) => entity.entityId.startsWith("sensor."));
    if (found) return found;
    return this._findByName(vehicle, terms, excludeTerms);
  }

  _findRovinietaStatus(vehicle) {
    const auto = this._findByName(
      vehicle,
      ["roviniet"],
      ["zile", "expir", "serie", "categorie", "perioad"],
      (entity) => entity.entityId.startsWith("sensor.") && this._isAutoRovinietaEntity(entity),
    );
    if (this._entityValue(auto)) return auto;

    return this._findByName(
      vehicle,
      ["roviniet", "status"],
      ["zile", "expir", "serie", "categorie", "perioad"],
      (entity) => entity.entityId.startsWith("sensor."),
    );
  }

  _findRovinietaDays(vehicle) {
    const auto = this._findByName(
      vehicle,
      ["roviniet", "zile", "ramase"],
      [],
      (entity) => entity.entityId.startsWith("sensor.") && this._isAutoRovinietaEntity(entity),
    );
    if (this._entityValue(auto) !== null) return auto;

    return this._findByName(
      vehicle,
      ["roviniet", "zile", "ramase"],
      [],
      (entity) => entity.entityId.startsWith("sensor."),
    );
  }

  _findRovinietaExpiry(vehicle) {
    const auto = this._findByName(
      vehicle,
      ["roviniet", "expir"],
      [],
      (entity) => this._isAutoRovinietaEntity(entity),
    );
    if (this._entityValue(auto)) return auto;

    return this._findByName(vehicle, ["roviniet", "expir"]);
  }

  _isAutoRovinietaEntity(entity) {
    const attrs = entity.stateObj?.attributes || {};
    return Boolean(
      attrs.numar_inmatriculare ||
      attrs.serie_rovinieta ||
      attrs.categorie_rovinieta ||
      attrs.numar_total_roviniete !== undefined ||
      attrs.detalii_rovinieta_activa
    );
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
    if (label.includes("e-rovinieta") || label === "rovinieta" || label.includes("rovinieta.ro")) return false;
    if (label.includes("car manager romania") && !group.plate) return false;

    const hasPlate = Boolean(group.plate);
    const hasCoreVehicleEntity = group.entities.some((entity) => {
      const name = this._normalize(this._friendly(entity));
      return name.includes("kilometri") || name.endsWith(" status") || name.includes("revizie") || name.includes("rca") || name.includes("itp");
    });
    const onlyRovinieta = group.entities.every((entity) => this._normalize(this._friendly(entity)).includes("roviniet"));
    const looksLikeVehicle = hasPlate || (hasCoreVehicleEntity && !onlyRovinieta);
    if (!looksLikeVehicle) return false;

    const isLicenseBlocked = group.entities.some((entity) => (entity.stateObj.attributes || {}).license_blocked);
    const inferredLicenseBlocked = this._shouldTreatUnavailableGroupAsLicenseLocked(group);
    if (inferredLicenseBlocked) group.license_blocked = true;

    // După dezactivarea manuală a unui autovehicul, Home Assistant păstrează
    // entitățile vechi ca unavailable. Le ascundem doar dacă NU sunt blocate
    // de licență; autovehiculele blocate de licență trebuie să rămână vizibile
    // în card ca placeholder.
    if (!group.hasAvailableEntity && !isLicenseBlocked && !inferredLicenseBlocked) return false;

    return true;
  }

  _shouldTreatUnavailableGroupAsLicenseLocked(group) {
    if (this._licenseAllowsPremiumFeatures()) return false;
    if (!group?.entities?.length) return false;
    if (group.hasAvailableEntity) return false;
    if (group.entities.some((entity) => (entity.stateObj.attributes || {}).license_blocked)) return true;

    const label = this._normalize(group.label || "");
    if (label.includes("car manager romania") || label.includes("e-rovinieta") || label.includes("rovinieta.ro")) return false;

    const hasVehicleIdentifiers = Boolean(group.vehicle_id || group.plate || group.vin || this._vehicleIdFromDevice(group.device || {}));
    const hasCoreVehicleEntity = group.entities.some((entity) => {
      const name = this._normalize(this._friendly(entity));
      return name.includes("kilometri") || name.endsWith(" status") || name.includes("revizie") || name.includes("rca") || name.includes("itp") || name.includes("casco") || name.includes("roviniet");
    });

    return hasVehicleIdentifiers || hasCoreVehicleEntity;
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


  _formatDisplayValue(value) {
    return this._formatDateForDisplay(value);
  }

  _formatDateForDisplay(value) {
    if (value === undefined || value === null) return value;
    const text = value.toString().trim();
    if (!text) return text;

    const isoMatch = text.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T\s].*)?$/);
    if (isoMatch) {
      return `${isoMatch[3]}/${isoMatch[2]}/${isoMatch[1]}`;
    }

    const roMatch = text.match(/^(\d{1,2})[\/.](\d{1,2})[\/.](\d{4})(?:\s.*)?$/);
    if (roMatch) {
      return `${roMatch[1].padStart(2, "0")}/${roMatch[2].padStart(2, "0")}/${roMatch[3]}`;
    }

    return text;
  }

  _formatMain(value) {
    if (value === undefined || value === null || value === "") return "—";
    return this._formatDisplayValue(value);
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
      .cmr-header-main { display: flex; align-items: center; gap: 12px; min-width: 0; }
      .cmr-header-text { min-width: 0; }
      .cmr-brand-icon { width: 88px; height: 88px; border-radius: 18px; object-fit: contain; flex: 0 0 auto; background: color-mix(in srgb, var(--primary-color) 10%, transparent); box-shadow: 0 8px 22px rgba(0,0,0,.12); }
      .cmr-brand-icon.is-hidden { display: none; }
      .cmr-header-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
      .cmr-tabs-wrap { margin-top: 14px; padding: 6px 8px 8px; border-radius: 18px; background: color-mix(in srgb, var(--card-background-color) 88%, var(--primary-color) 12%); border: 1px solid var(--divider-color); }
      .cmr-tabs { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 1px; align-items: center; }
      .cmr-tab { min-width: 0; min-height: 32px; border: 0; border-radius: 999px; padding: 6px 2px; color: var(--secondary-text-color); background: transparent; cursor: pointer; line-height: 1; }
      .cmr-tab ha-icon { width: 18px; height: 18px; display: block; margin: 0 auto; transition: transform .14s ease, color .14s ease; }
      .cmr-tab:hover ha-icon, .cmr-tab:focus-visible ha-icon { transform: translateY(-1px) scale(1.08); }
      .cmr-tab.is-active { color: var(--primary-text-color); background: color-mix(in srgb, var(--primary-color) 22%, transparent); }
      .cmr-tab.is-active ha-icon { transform: scale(1.08); }
      .cmr-tab-current { min-height: 24px; margin-top: 6px; display: flex; align-items: center; justify-content: center; text-align: center; font-size: 15px; font-weight: 900; line-height: 1.2; color: var(--primary-text-color); letter-spacing: .01em; opacity: 0; transition: opacity .14s ease; }
      .cmr-tab-current.has-label { opacity: 1; }
      @media (max-width: 360px) {
        .cmr-tabs-wrap { padding-left: 6px; padding-right: 6px; }
        .cmr-tabs { gap: 0; }
        .cmr-tab { min-height: 30px; padding-left: 1px; padding-right: 1px; }
        .cmr-tab ha-icon { width: 17px; height: 17px; }
        .cmr-tab-current { font-size: 14px; min-height: 22px; }
      }
      .cmr-title { font-size: 20px; font-weight: 800; letter-spacing: -0.02em; }
      .cmr-subtitle, .cmr-plate, .cmr-row-muted, .cmr-tile-sub { color: var(--secondary-text-color); font-size: 12px; }
      .cmr-mode, .cmr-action { border: 0; border-radius: 999px; padding: 8px 12px; color: var(--primary-text-color); background: color-mix(in srgb, var(--primary-color) 14%, transparent); cursor: pointer; font-weight: 700; }
      .cmr-mode[disabled], .cmr-action[disabled] { opacity: .6; cursor: wait; }
      .cmr-secondary { background: color-mix(in srgb, var(--secondary-text-color) 12%, transparent); }
      .cmr-backup-panel { margin-top: 14px; padding: 14px; border-radius: 18px; background: color-mix(in srgb, var(--card-background-color) 86%, var(--primary-color) 14%); border: 1px solid var(--divider-color); }
      .cmr-backup-text, .cmr-backup-note { color: var(--secondary-text-color); font-size: 12px; line-height: 1.35; margin-top: 6px; }
      .cmr-backup-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
      .cmr-license-panel { margin-top: 14px; padding: 14px; border-radius: 18px; background: color-mix(in srgb, var(--card-background-color) 86%, var(--primary-color) 14%); border: 1px solid var(--divider-color); }
      .cmr-section-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
      .cmr-section-title { font-size: 16px; font-weight: 900; }
      .cmr-section-subtitle { margin-top: 3px; color: var(--secondary-text-color); font-size: 12px; line-height: 1.35; }
      .cmr-license-badge { border-radius: 999px; padding: 6px 10px; font-size: 12px; font-weight: 900; white-space: nowrap; background: color-mix(in srgb, var(--secondary-text-color) 12%, transparent); }
      .cmr-license-badge.is-good { background: color-mix(in srgb, var(--success-color, #43a047) 20%, transparent); color: var(--primary-text-color); }
      .cmr-license-badge.is-warn { background: color-mix(in srgb, var(--warning-color, #ffa000) 22%, transparent); color: var(--primary-text-color); }
      .cmr-license-badge.is-bad { background: color-mix(in srgb, var(--error-color, #e53935) 18%, transparent); color: var(--primary-text-color); }
      .cmr-license-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-bottom: 12px; }
      .cmr-license-info { padding: 10px; border-radius: 14px; background: color-mix(in srgb, var(--card-background-color) 78%, var(--secondary-text-color) 8%); border: 1px solid var(--divider-color); min-width: 0; }
      .cmr-license-label { color: var(--secondary-text-color); font-size: 11px; font-weight: 800; margin-bottom: 4px; }
      .cmr-license-value { font-size: 13px; font-weight: 800; overflow-wrap: anywhere; }
      .cmr-license-form { display: grid; gap: 10px; }
      .cmr-license-form label { display: grid; gap: 5px; font-size: 12px; color: var(--secondary-text-color); font-weight: 800; }
      .cmr-license-form input { width: 100%; box-sizing: border-box; border-radius: 12px; border: 1px solid var(--divider-color); padding: 10px 11px; background: var(--card-background-color); color: var(--primary-text-color); font: inherit; }
      .cmr-license-actions { display: flex; flex-wrap: wrap; gap: 8px; }
      .cmr-license-donation-note { margin: -2px 0 10px; color: var(--secondary-text-color); font-size: 12px; line-height: 1.35; }
      .cmr-bmc-button { display: inline-flex; align-items: center; justify-content: center; gap: 8px; width: fit-content; max-width: 100%; box-sizing: border-box; margin: 0 0 12px; padding: 8px 13px; border-radius: 999px; background: #FFDD00; border: 1px solid #000000; color: #000000; text-decoration: none; font-size: 14px; font-weight: 900; line-height: 1; box-shadow: 0 2px 0 rgba(0,0,0,.18); }
      .cmr-bmc-button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
      .cmr-bmc-emoji { font-size: 17px; line-height: 1; }
      .cmr-backup-field { margin-top: 10px; }
      .cmr-vehicle { margin-top: 16px; padding: 14px; border-radius: 18px; background: color-mix(in srgb, var(--card-background-color) 86%, var(--primary-color) 14%); border: 1px solid var(--divider-color); }
      .cmr-license-locked-vehicle { background: color-mix(in srgb, var(--card-background-color) 88%, var(--secondary-text-color) 12%); border: 1px dashed color-mix(in srgb, var(--secondary-text-color) 55%, var(--divider-color)); opacity: .86; }
      .cmr-locked-head { display: flex; align-items: center; gap: 10px; }
      .cmr-locked-icon { width: 34px; height: 34px; border-radius: 999px; display: flex; align-items: center; justify-content: center; background: color-mix(in srgb, var(--secondary-text-color) 16%, transparent); color: var(--secondary-text-color); flex: 0 0 auto; }
      .cmr-locked-icon ha-icon { width: 20px; height: 20px; }
      .cmr-license-locked-body { margin-top: 12px; color: var(--secondary-text-color); font-size: 12px; line-height: 1.4; }
      .cmr-license-locked-actions { margin-top: 12px; display: flex; justify-content: flex-start; }
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
      .cmr-cost-summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px; margin-top: 10px; }
      .cmr-fuel-head { align-items: flex-end; }
      .cmr-fuel-head-actions { display: flex; align-items: flex-end; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
      .cmr-info-note { margin: 8px 0; padding: 9px 10px; border: 1px solid rgba(68, 180, 213, .32); border-radius: 12px; background: rgba(68, 180, 213, .10); color: var(--secondary-text-color); font-size: 12px; line-height: 1.35; }
      .cmr-fuel-filter { display: flex; flex-direction: column; gap: 4px; min-width: 170px; font-size: 11px; color: var(--secondary-text-color); font-weight: 900; }
      .cmr-fuel-filter select { width: 100%; border: 1px solid var(--divider-color); border-radius: 10px; padding: 7px 9px; background: var(--card-background-color); color: var(--primary-text-color); font-weight: 800; }
      .cmr-recent-title { margin: 10px 0 6px; font-size: 12px; font-weight: 900; color: var(--secondary-text-color); }
      .cmr-check { display: flex; align-items: center; gap: 8px; margin: 8px 0; font-size: 13px; font-weight: 800; }
      .cmr-cost-card { padding: 12px; border-radius: 16px; background: var(--card-background-color); border: 1px solid var(--divider-color); }
      .cmr-cost-title { color: var(--secondary-text-color); font-size: 12px; font-weight: 900; }
      .cmr-cost-value { margin-top: 6px; font-size: 20px; font-weight: 950; letter-spacing: -0.02em; }
      .cmr-cost-section { margin-top: 14px; padding: 12px; border-radius: 16px; background: color-mix(in srgb, var(--card-background-color) 92%, var(--primary-color) 8%); }
      .cmr-cost-table { display: flex; flex-direction: column; gap: 0; }
      .cmr-cost-table-row { display: grid; grid-template-columns: minmax(0, 1.35fr) repeat(3, minmax(72px, .55fr)); gap: 8px; align-items: center; padding: 9px 0; border-top: 1px solid color-mix(in srgb, var(--divider-color) 70%, transparent); }
      .cmr-cost-table-wide .cmr-cost-table-row { grid-template-columns: minmax(0, 1.4fr) repeat(5, minmax(70px, .55fr)); }
      .cmr-cost-table-row:first-child { border-top: 0; }
      .cmr-cost-table-row span { min-width: 0; overflow-wrap: anywhere; }
      .cmr-cost-table-row small { display: block; color: var(--secondary-text-color); font-size: 11px; margin-top: 2px; }
      .cmr-cost-table-head { color: var(--secondary-text-color); font-size: 11px; font-weight: 900; text-transform: uppercase; letter-spacing: .03em; }
      .cmr-vehicle-cost-list { display: flex; flex-direction: column; gap: 10px; }
      .cmr-vehicle-cost-card { background: color-mix(in srgb, var(--card-background-color) 78%, black); border: 1px solid color-mix(in srgb, var(--divider-color) 75%, transparent); border-radius: 14px; padding: 12px; }
      .cmr-vehicle-cost-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
      .cmr-vehicle-cost-head strong { display: block; font-size: 14px; line-height: 1.25; overflow-wrap: anywhere; }
      .cmr-vehicle-cost-head small { display: block; color: var(--secondary-text-color); font-size: 11px; margin-top: 3px; overflow-wrap: anywhere; }
      .cmr-vehicle-cost-total { flex: 0 0 auto; font-weight: 900; font-size: 15px; white-space: nowrap; }
      .cmr-vehicle-cost-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
      .cmr-vehicle-cost-grid div { background: color-mix(in srgb, var(--secondary-background-color) 75%, transparent); border-radius: 10px; padding: 8px; min-width: 0; }
      .cmr-vehicle-cost-grid span { display: block; color: var(--secondary-text-color); font-size: 10px; font-weight: 800; text-transform: uppercase; margin-bottom: 4px; }
      .cmr-vehicle-cost-grid strong { display: block; font-size: 13px; white-space: nowrap; }
      .cmr-cost-chips { display: flex; flex-wrap: wrap; gap: 8px; }
      .cmr-cost-chip { display: flex; gap: 8px; align-items: center; padding: 8px 10px; border-radius: 999px; background: var(--card-background-color); border: 1px solid var(--divider-color); }
      .cmr-cost-chip span { color: var(--secondary-text-color); font-size: 12px; font-weight: 800; }
      .cmr-cost-chip strong { font-size: 12px; }
      .cmr-cost-list { display: flex; flex-direction: column; gap: 8px; }
      .cmr-equipment-missing { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
      .cmr-equipment-required-card { display: block; min-width: 0; width: 100%; box-sizing: border-box; padding: 10px; border-radius: 14px; background: var(--card-background-color); border: 1px solid var(--divider-color); }
      .cmr-equipment-required-head { display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap; min-width: 0; }
      .cmr-equipment-required-head strong { display: inline; min-width: 0; font-weight: 900; line-height: 1.25; white-space: normal; overflow-wrap: normal; word-break: normal; hyphens: auto; }
      .cmr-equipment-required-head span { color: var(--secondary-text-color); font-size: 12px; font-weight: 700; white-space: nowrap; }
      .cmr-equipment-required-note { margin-top: 5px; color: var(--secondary-text-color); font-size: 12px; line-height: 1.35; overflow-wrap: normal; word-break: normal; }
      .cmr-equipment-required-actions { display: flex; flex-wrap: wrap; justify-content: flex-start; gap: 6px; margin-top: 9px; }
      .cmr-cost-item { display: flex; justify-content: space-between; gap: 10px; align-items: center; padding: 10px; border-radius: 14px; background: var(--card-background-color); border: 1px solid var(--divider-color); }
      .cmr-cost-item-with-actions, .cmr-cost-item-block { align-items: flex-start; flex-wrap: wrap; }
      .cmr-cost-item-block .cmr-cost-item-main { flex: 1 1 180px; }
      .cmr-cost-item-main { min-width: 0; flex: 1 1 220px; }
      .cmr-cost-item-side { display: flex; flex-direction: column; align-items: flex-end; gap: 8px; flex: 0 0 auto; }
      .cmr-inline-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px; }
      .cmr-inline-edit-form { flex: 1 0 100%; margin-top: 8px; }
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
        .cmr-header, .cmr-vehicle-head, .cmr-fuel-head { align-items: flex-start; }
        .cmr-header { flex-direction: column; }
        .cmr-brand-icon { width: 76px; height: 76px; border-radius: 16px; }
        .cmr-header-actions { width: 100%; justify-content: flex-start; }
        .cmr-add-grid, .cmr-cost-summary-grid, .cmr-license-grid { grid-template-columns: 1fr; }
        .cmr-fuel-head { flex-direction: column; }
        .cmr-fuel-head-actions { width: 100%; justify-content: flex-start; }
        .cmr-fuel-filter { width: 100%; }
        .cmr-field { grid-template-columns: 1fr; }
        .cmr-service-grid { grid-template-columns: 1fr; }
        .cmr-history-row { flex-direction: column; }
        .cmr-cost-item-block, .cmr-equipment-warning { flex-direction: column; align-items: flex-start; }
        .cmr-cost-item-block .cmr-cost-item-main, .cmr-equipment-warning .cmr-cost-item-main { width: 100%; flex-basis: auto; }
        .cmr-cost-item-side { align-items: flex-start; width: 100%; }
        .cmr-inline-actions { justify-content: flex-start; }
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
