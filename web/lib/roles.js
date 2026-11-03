import Link from "next/link";

// Role groups mirror the backend RBAC sets. Keep in sync with core/rbac.py.
export const GROUPS = {
  seller: ["farmer", "fpo"],
  buyer: ["buyer_household", "buyer_business"],
  shopper: ["farmer", "fpo", "buyer_household", "buyer_business"],
  agent: ["field_agent", "mandal_manager", "superadmin"],
  advisor: ["farmer", "fpo", "agronomist", "field_agent", "mandal_manager", "superadmin"],
  carrier: ["transport", "mandal_manager", "superadmin"],
  staff: ["superadmin", "finance", "mandal_manager", "support"],
  financeStaff: ["finance", "superadmin"],
};

export const ROLE_LABEL = {
  farmer: "Farmer", fpo: "FPO", buyer_household: "Household buyer",
  buyer_business: "Business buyer", field_agent: "Field agent",
  agronomist: "Agronomist", transport: "Transport partner",
  support: "Support", mandal_manager: "Mandal manager",
  finance: "Finance", superadmin: "Superadmin",
};

/**
 * Pure render-gate (NOT a hook): call it after all hooks, where a page would
 * otherwise early-return its "log in" prompt. Returns JSX to render when the
 * viewer may not use the page, or null when access is allowed.
 *   const gate = roleGate(me, GROUPS.seller); if (gate) return gate;
 */
export function roleGate(me, allow, { label = "this section" } = {}) {
  if (!me) {
    return (
      <div>
        <p className="muted">Please log in to continue.</p>
        <Link href="/login" className="btn">Login</Link>
      </div>
    );
  }
  if (allow && !allow.includes(me.role)) {
    return (
      <div className="card" style={{ maxWidth: 520, borderLeft: "4px solid var(--amber-600)" }}>
        <h2 style={{ marginTop: 0 }}>Not available for your role</h2>
        <p className="muted">
          {label[0].toUpperCase() + label.slice(1)} is not part of the{" "}
          <b>{ROLE_LABEL[me.role] || me.role}</b> workspace.
        </p>
        <Link href="/dashboard" className="btn">Go to my dashboard</Link>
      </div>
    );
  }
  return null;
}
