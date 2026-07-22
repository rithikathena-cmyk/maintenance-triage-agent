"""Seed the queue with sample work orders.

Run from the project root:  python -m backend.database.seed

Includes a mix of routine orders and several with injury-risk language so the
safety guard and top-of-list sorting are visible immediately.
"""
from backend.database.database import SessionLocal, init_db
from backend.database import models

SAMPLE_ORDERS = [
    # ---- Injury / hazard risk (safety rule should force safety-critical) ----
    {
        "title": "Hydraulic press #2 leaking near guard",
        "description": "Press #2 is leaking hydraulic fluid onto the floor by the pinch point. The safety guard was removed and not put back — operator could get caught in the ram.",
        "location": "Line A - Press #2",
        "reported_by": "operator.j.rivera",
    },
    {
        "title": "Coolant spill around grinder",
        "description": "Coolant has spilled across the walkway by the surface grinder. Slip hazard and someone could be injured.",
        "location": "Cell 1 - Surface Grinder",
        "reported_by": "operator.d.okafor",
    },
    {
        "title": "Robot cell E-stop not latching",
        "description": "The emergency stop on the welding robot cell doesn't latch reliably — it may not stop the arm. Serious injury risk if it fails.",
        "location": "Weld Cell 2",
        "reported_by": "operator.k.abara",
    },
    {
        "title": "Exposed wiring at drive cabinet",
        "description": "A wire is hanging loose and energized inside the open drive cabinet on the mill. Arc flash and electric shock risk to anyone reaching in.",
        "location": "Cell 4 - Vertical Mill",
        "reported_by": "operator.b.lindqvist",
    },
    {
        "title": "Overhead crane hoist chain slipping",
        "description": "The hoist on the bay crane slips under load and drops a few inches at a time. A load could fall and crush someone working below.",
        "location": "Bay 2 - Overhead Crane",
        "reported_by": "operator.p.osei",
    },
    {
        "title": "Band saw guard missing",
        "description": "The blade guard on the horizontal band saw is missing entirely. Exposed moving blade — laceration or amputation risk.",
        "location": "Saw Station",
        "reported_by": "operator.h.tanaka",
    },
    {
        "title": "Solvent fumes in finishing booth",
        "description": "Strong solvent fumes in the finishing booth; the exhaust fan isn't running. Operator felt dizzy — toxic fumes with no ventilation.",
        "location": "Finishing Booth 1",
        "reported_by": "operator.n.acosta",
    },
    {
        "title": "Forklift brakes soft",
        "description": "The warehouse forklift brakes feel soft and it barely stopped near the pedestrian aisle. Someone could be hit.",
        "location": "Shipping - Forklift 3",
        "reported_by": "operator.c.dubois",
    },

    # ---- Production-stopping (machine down / scrap, but not a hazard) ----
    {
        "title": "CNC #4 out of calibration",
        "description": "CNC #4 is machining parts 0.3mm out of tolerance. Not dangerous, but every part is scrap so the cell is stopped.",
        "location": "Cell 3 - CNC #4",
        "reported_by": "operator.m.chen",
    },
    {
        "title": "Injection molder heater band down",
        "description": "One heater band on the injection molder failed; barrel won't reach temperature so the machine is down. No hazard.",
        "location": "Molding - Machine 3",
        "reported_by": "operator.r.singh",
    },
    {
        "title": "Air compressor tripped offline",
        "description": "The main air compressor tripped and won't restart. The whole assembly line lost pneumatic pressure and is stopped. No injury risk.",
        "location": "Utilities - Compressor Room",
        "reported_by": "operator.f.moreau",
    },
    {
        "title": "Conveyor drive fault on Line B",
        "description": "The main conveyor drive throws a fault code and won't run, so Line B is halted. Safe state, nobody at risk.",
        "location": "Line B - Main Conveyor",
        "reported_by": "operator.s.patel",
    },
    {
        "title": "Packaging PLC faulted",
        "description": "The PLC on the packaging line faulted out and the line is down. It stopped safely; not a safety concern, just no output.",
        "location": "Packaging - Line 1",
        "reported_by": "operator.y.kim",
    },
    {
        "title": "Lathe #1 chuck won't clamp",
        "description": "Lathe #1 hydraulic chuck won't clamp the workpiece, so we can't run any parts. No danger, just idle.",
        "location": "Cell 2 - Lathe #1",
        "reported_by": "operator.t.nguyen",
    },
    {
        "title": "Broken tap stuck in fixture",
        "description": "A tap snapped off in the drilling fixture and jammed it. The station is down until it's extracted. Not hazardous.",
        "location": "Cell 5 - Drill Fixture",
        "reported_by": "operator.a.varga",
    },

    # ---- Routine (degraded / cosmetic, production continues) ----
    {
        "title": "Flickering control panel on conveyor",
        "description": "The control panel display on the conveyor flickers now and then. Line still runs fine.",
        "location": "Line B - Conveyor Panel",
        "reported_by": "operator.s.patel",
    },
    {
        "title": "Lathe spindle bearing noise",
        "description": "Lathe #1 spindle makes a faint grinding noise at high RPM. Still cuts within tolerance; worth checking the bearing eventually.",
        "location": "Cell 2 - Lathe #1",
        "reported_by": "operator.t.nguyen",
    },
    {
        "title": "Slow coolant drip at fitting",
        "description": "A fitting on the CNC coolant line drips slowly into the tray. Contained, not a hazard, just a nuisance.",
        "location": "Cell 3 - CNC #4",
        "reported_by": "operator.m.chen",
    },
    {
        "title": "HMI touchscreen unresponsive in one corner",
        "description": "The bottom-left of the HMI touchscreen is slow to respond. Operators tap twice; there's an easy workaround.",
        "location": "Molding - Machine 3",
        "reported_by": "operator.r.singh",
    },
    {
        "title": "Faded label on tool cabinet",
        "description": "The label on tooling cabinet drawer 4 has worn off. Purely cosmetic.",
        "location": "Tool Crib",
        "reported_by": "operator.l.gomez",
    },
    {
        "title": "Worn floor tape near cell 1",
        "description": "The yellow floor marking tape by cell 1 is peeling. Cosmetic, aisle is still clearly marked.",
        "location": "Cell 1",
        "reported_by": "operator.d.okafor",
    },
]


def seed():
    init_db()
    db = SessionLocal()
    try:
        existing = db.query(models.WorkOrder).count()
        if existing:
            print(f"Database already has {existing} work orders; skipping seed.")
            return
        for order in SAMPLE_ORDERS:
            db.add(models.WorkOrder(status=models.STATUS_PENDING, **order))
        db.commit()
        print(f"Seeded {len(SAMPLE_ORDERS)} work orders.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
