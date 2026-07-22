"""Add a further, *deliberately different* batch of sample work orders.

Additive and idempotent (de-dupes by title), like ``seed_extra`` — run it
repeatedly to top up the queue:

    python -m backend.database.seed_more

What makes this batch different from ``seed.py`` / ``seed_extra.py``:

  * New equipment & departments not covered before — HVAC, plating/anodize,
    AGVs, dust collection, QC lab (CMM), loading dock, water treatment, fire
    suppression, IT-on-the-floor, forklift charging, etc.
  * Varied submission times (``age_hours``) so the queue has a realistic
    spread across the last several days instead of all-at-once timestamps.
  * A few NEGATED-hazard edge cases ("no injury risk", "not a slip hazard")
    that mention safety words but should NOT escalate — these exercise the
    negator branch in ``safety_rules.detect_safety`` that the other seeds miss.
"""
from datetime import datetime, timedelta

from backend.database.database import SessionLocal, init_db
from backend.database import models

# Each row may carry an optional ``age_hours`` — how long ago it was "filed".
MORE_ORDERS = [
    # ---- Injury / hazard risk (new domains; safety guard should escalate) ----
    {
        "title": "Anodize tank acid splash on rim",
        "description": "The anodize line tank is bubbling over and splashing sulfuric acid onto the walkway grating. Chemical burn risk to anyone loading racks.",
        "location": "Plating - Anodize Line",
        "reported_by": "operator.v.petrov",
        "age_hours": 1,
    },
    {
        "title": "AGV not stopping for pedestrians",
        "description": "The automated guided vehicle on the north route isn't slowing when someone steps into its path — the safety scanner seems blind on one side. Could strike a worker.",
        "location": "Logistics - AGV Route N",
        "reported_by": "operator.s.yamamoto",
        "age_hours": 3,
    },
    {
        "title": "Dust collector sparking at inlet",
        "description": "The baghouse dust collector is throwing sparks at the duct inlet near combustible aluminium dust. Fire and explosion hazard.",
        "location": "Finishing - Dust Collector",
        "reported_by": "operator.d.mwangi",
        "age_hours": 6,
    },
    {
        "title": "Loading dock leveler dropping unexpectedly",
        "description": "The dock leveler plate drops on its own while a worker is on it. Someone could fall into the dock gap or be crushed between trailer and dock.",
        "location": "Shipping - Dock 4",
        "reported_by": "operator.a.kowalski",
        "age_hours": 20,
    },
    {
        "title": "Boiler low-water cutoff not tripping",
        "description": "The boiler's low-water cutoff didn't trip on test. If it fails for real the boiler could run dry and rupture — explosion and scald hazard.",
        "location": "Utilities - Boiler Room",
        "reported_by": "operator.t.oconnell",
        "age_hours": 30,
    },
    {
        "title": "Live 480V at cooling tower disconnect",
        "description": "The cooling tower disconnect reads energized with the handle in OFF. Anyone servicing the fan motor risks electrocution — lockout can't be trusted.",
        "location": "Roof - Cooling Tower 2",
        "reported_by": "operator.r.delacruz",
        "age_hours": 52,
    },

    # ---- Production-stopping (new equipment; machine down, no hazard) ----
    {
        "title": "Powder coat oven won't reach setpoint",
        "description": "The powder coat cure oven tops out 40°C below setpoint, so nothing cures and the finishing line is stopped. No hazard, just no throughput.",
        "location": "Finishing - Cure Oven",
        "reported_by": "operator.m.oliveira",
        "age_hours": 2,
    },
    {
        "title": "CMM probe calibration lost in QC lab",
        "description": "The coordinate measuring machine lost probe calibration and rejects its own artifact check, so first-article inspection is blocked. Not dangerous, just halted.",
        "location": "QC Lab - CMM",
        "reported_by": "inspector.l.bianchi",
        "age_hours": 5,
    },
    {
        "title": "Pallet wrapper turntable seized",
        "description": "The stretch-wrap turntable won't rotate, so finished pallets can't be wrapped for shipment and the line backs up. Machine is stopped and safe.",
        "location": "Shipping - Pallet Wrapper",
        "reported_by": "operator.a.kowalski",
        "age_hours": 9,
    },
    {
        "title": "DI water system offline for wash line",
        "description": "The deionized water system faulted and the parts wash line has no rinse water, so we stopped it to avoid spotting. Nobody at risk.",
        "location": "Utilities - DI Water Skid",
        "reported_by": "operator.k.andersson",
        "age_hours": 26,
    },
    {
        "title": "Floor network switch down, scanners offline",
        "description": "The shop-floor network switch in the east panel died and all the handheld scanners lost connection, so production reporting is stopped. No safety impact.",
        "location": "IT - East Network Cabinet",
        "reported_by": "tech.j.nakamura",
        "age_hours": 44,
    },
    {
        "title": "Welding positioner drive faulted",
        "description": "The rotary welding positioner throws a drive fault and won't index, so the weld cell can't run the fixture. Safe stop, just idle.",
        "location": "Weld Cell 3 - Positioner",
        "reported_by": "operator.g.fischer",
        "age_hours": 70,
    },

    # ---- Routine (new items; degraded / cosmetic) ----
    {
        "title": "HVAC rooftop unit short-cycling",
        "description": "The office-side rooftop HVAC unit short-cycles and the area runs a bit warm. Comfort issue only; production areas unaffected.",
        "location": "Roof - RTU 1",
        "reported_by": "facilities.p.romano",
        "age_hours": 4,
    },
    {
        "title": "Exit sign LED out by break room",
        "description": "One letter of the illuminated EXIT sign by the break room is out. Still legible; replace the LED strip at convenience.",
        "location": "Break Room Corridor",
        "reported_by": "facilities.p.romano",
        "age_hours": 33,
    },
    {
        "title": "Torque wrench overdue for calibration",
        "description": "The assembly torque wrench is a week past its calibration due date. Still reads consistent on the checker; schedule recal at next PM.",
        "location": "Assembly - Tool Board",
        "reported_by": "operator.t.owusu",
        "age_hours": 55,
    },
    {
        "title": "Squeegee worn on parts washer",
        "description": "The drying squeegee on the parts washer exit is worn and leaves a few drips. Parts still pass; swap the blade when a spare arrives.",
        "location": "Wash Line - Exit",
        "reported_by": "operator.k.andersson",
        "age_hours": 78,
    },
    {
        "title": "Forklift charger fan noisy",
        "description": "The fan in forklift charger bay 2 is louder than usual but still charges to full overnight. Monitor; not urgent.",
        "location": "Charging - Bay 2",
        "reported_by": "operator.c.dubois",
        "age_hours": 100,
    },

    # ---- NEGATED-hazard edge cases (mention safety words but should NOT escalate) ----
    {
        "title": "Gate proximity sensor faulting intermittently",
        "description": "The proximity sensor on the guard gate faults now and then and stops the cell. There is no injury risk — the gate stays closed and the machine is safe; it's purely a nuisance trip.",
        "location": "Cell 5 - Guard Gate",
        "reported_by": "operator.a.varga",
        "age_hours": 7,
    },
    {
        "title": "Thin oil film near press, already cordoned",
        "description": "A thin oil film appeared by the press. It is not a slip hazard — the area is already cordoned and being wiped down. Logging so maintenance checks the seal source.",
        "location": "Line A - Press #2",
        "reported_by": "operator.j.rivera",
        "age_hours": 12,
    },

    # ---- Ambiguous judgement call (new) ----
    {
        "title": "Intermittent smell of hot plastic at extruder",
        "description": "Every so often there's a smell of hot plastic near the extruder, then it clears. Output looks normal and temps read in range, but nobody's sure if a heater is degrading.",
        "location": "Extrusion - Line 1",
        "reported_by": "operator.r.singh",
        "age_hours": 15,
    },
]


def seed_more():
    init_db()
    db = SessionLocal()
    try:
        existing_titles = {t for (t,) in db.query(models.WorkOrder.title).all()}
        now = datetime.utcnow()
        added = 0
        for order in MORE_ORDERS:
            if order["title"] in existing_titles:
                continue
            data = {k: v for k, v in order.items() if k != "age_hours"}
            created_at = now - timedelta(hours=order.get("age_hours", 0))
            db.add(models.WorkOrder(
                status=models.STATUS_PENDING, created_at=created_at, **data
            ))
            added += 1
        db.commit()
        skipped = len(MORE_ORDERS) - added
        print(f"Added {added} new work orders" + (f" (skipped {skipped} already present)." if skipped else "."))
    finally:
        db.close()


if __name__ == "__main__":
    seed_more()
