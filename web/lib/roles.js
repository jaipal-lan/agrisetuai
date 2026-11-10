import Link from "next/link";

// Role groups mirror the backend RBAC sets. Keep in sync with core/rbac.py.
export const GROUPS = {
  seller: ["farmer"],
  buyer: ["buyer_household", "buyer_business"],
  // A farmer can also buy, so "shopper" (market/offers/orders) spans both.
  shopper: ["farmer", "buyer_household", "buyer_business"],
  agent: ["field_agent", "field_leader", "field_manager", "superadmin"],
  lead: ["field_leader", "field_manager", "superadmin"],
  carrier: ["transport", "field_leader", "field_manager", "superadmin"],
  staff: ["superadmin", "field_manager", "field_leader"],
};

export const ROLE_LABEL = {
  farmer: "Farmer", buyer_household: "Household buyer",
  buyer_business: "Business buyer", field_agent: "Field agent",
  field_leader: "Field leader", field_manager: "Field manager",
  transport: "Transport partner", superadmin: "Superadmin",
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
