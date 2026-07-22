"""Add MORE sample work orders to an already-seeded queue.

Unlike ``seed.py`` (which refuses to run once the table is non-empty), this
script is *additive and idempotent*: it inserts only orders whose title isn't
already present, so you can run it repeatedly to top up the queue.

Run from the project root:  python -m backend.database.seed_extra

The extra set widens coverage across all three urgency bands — more injury /
hazard language for the safety guard, more machine-down cases, and more routine
nuisances — plus a few ambiguous ones that exercise the model's judgement.
"""
from backend.database.database import SessionLocal, init_db
from backend.database import models

EXTRA_ORDERS = [
    # ---- Injury / hazard risk (safety rule should force safety-critical) ----
    {
        "title": "Frayed sling on jib crane",
        "description": "The lifting sling on the jib crane at the assembly bench is frayed and starting to unravel. If it snaps under load the part could drop on the assembler below — serious injury risk.",
        "location": "Assembly - Jib Crane",
        "reported_by": "operator.g.fischer",
    },
    {
        "title": "Steam line pinhole leak burning hot",
        "description": "A pinhole leak on the overhead steam line is venting scalding steam right over the walkway. Anyone passing under could get badly burned.",
        "location": "Utilities - Steam Header",
        "reported_by": "operator.m.rossi",
    },
    {
        "title": "Guard interlock bypassed on press brake",
        "description": "Someone taped over the light-curtain interlock on the press brake so it runs with the guard open. Operator's hands are inside the die area while it cycles — amputation hazard.",
        "location": "Fab - Press Brake 1",
        "reported_by": "operator.s.haddad",
    },
    {
        "title": "Nitrogen leak in enclosed room",
        "description": "Hissing from the nitrogen manifold in the small laser room; the door was closed. Asphyxiation risk if oxygen is displaced and someone works in there.",
        "location": "Laser Room",
        "reported_by": "operator.w.zhang",
    },
    {
        "title": "Ladder rung cracked on mezzanine access",
        "description": "The third rung of the fixed ladder up to the mezzanine is cracked and flexes when stepped on. Someone could fall from height.",
        "location": "Warehouse - Mezzanine",
        "reported_by": "operator.k.novak",
    },
    {
        "title": "Molten metal splash at die cast",
        "description": "The die-cast machine is spitting molten aluminium past the splash shield toward the operator station. Burn hazard on every shot.",
        "location": "Die Cast - Cell 1",
        "reported_by": "operator.j.mendez",
    },
    {
        "title": "Chemical drum leaking near drain",
        "description": "A drum of degreaser is leaking and the puddle is spreading toward the floor drain. Toxic and a slip hazard; fumes are noticeable.",
        "location": "Wash Bay",
        "reported_by": "operator.e.johansson",
    },

    # ---- Production-stopping (machine down / scrap, but not a hazard) ----
    {
        "title": "Servo drive alarm on Router 2",
        "description": "The X-axis servo drive faults with an overcurrent alarm and won't reset, so the CNC router is dead. Safe, but zero output on that cell.",
        "location": "Cell 6 - CNC Router 2",
        "reported_by": "operator.d.walsh",
    },
    {
        "title": "Vision system rejecting every part",
        "description": "The inline vision inspection is failing 100% of good parts after a lighting change, so the line auto-stops. Nothing is dangerous, it's just blocked.",
        "location": "Line C - Inspection",
        "reported_by": "operator.a.ferreira",
    },
    {
        "title": "Chiller down, molds overheating",
        "description": "The process chiller quit and mold temps are climbing, so we had to stop molding before parts flash. No hazard, but production is halted.",
        "location": "Molding - Chiller Loop",
        "reported_by": "operator.r.singh",
    },
    {
        "title": "Labeler jamming every cycle",
        "description": "The end-of-line labeler jams on every carton and stops the conveyor. Not a safety issue; the packaging line can't ship.",
        "location": "Packaging - Line 2",
        "reported_by": "operator.y.kim",
    },
    {
        "title": "Spindle won't reach commanded RPM",
        "description": "Mill spindle tops out at 4000 RPM instead of 12000 and throws a drive fault, so we can't run the program. Idle, not unsafe.",
        "location": "Cell 4 - Vertical Mill",
        "reported_by": "operator.b.lindqvist",
    },
    {
        "title": "Feeder bowl not indexing parts",
        "description": "The vibratory feeder bowl stopped presenting parts to the assembly robot, starving the cell. It stopped safely; just no throughput.",
        "location": "Assembly - Robot Cell 1",
        "reported_by": "operator.t.owusu",
    },
    {
        "title": "Barcode scanner dead at pick station",
        "description": "The fixed barcode scanner at the pick-and-pack station is unresponsive, so orders can't be confirmed and shipping is stopped. No danger.",
        "location": "Shipping - Pick Station",
        "reported_by": "operator.c.dubois",
    },

    # ---- Routine (degraded / cosmetic, production continues) ----
    {
        "title": "Cooling fan rattle in control cabinet",
        "description": "A cabinet cooling fan has a slight rattle. Temps are still normal and the cell runs fine; worth swapping the fan at the next PM.",
        "location": "Cell 6 - Control Cabinet",
        "reported_by": "operator.d.walsh",
    },
    {
        "title": "Gauge lens fogged on air dryer",
        "description": "The pressure gauge lens on the air dryer is fogged and hard to read. The dryer works; purely a readability nuisance.",
        "location": "Utilities - Air Dryer",
        "reported_by": "operator.f.moreau",
    },
    {
        "title": "Squeaky caster on tool cart",
        "description": "One caster on the shared tool cart squeaks and sticks a bit. Annoying but the cart rolls fine.",
        "location": "Tool Crib",
        "reported_by": "operator.l.gomez",
    },
    {
        "title": "Timestamp drift on line printer",
        "description": "The date/time on the traceability printer is a few minutes off. Labels still print; just needs a clock sync.",
        "location": "Packaging - Line 1",
        "reported_by": "operator.y.kim",
    },
    {
        "title": "Loose access panel screw on conveyor",
        "description": "One of the four screws on a conveyor access panel is missing. Panel is still secure with three; replace at convenience.",
        "location": "Line B - Conveyor",
        "reported_by": "operator.s.patel",
    },
    {
        "title": "Dim work light over inspection bench",
        "description": "One LED tube over the inspection bench is dimmer than the others. Still plenty of light to work; swap when a spare is handy.",
        "location": "QC - Inspection Bench",
        "reported_by": "operator.n.acosta",
    },

    # ---- Ambiguous / judgement calls (no obvious keyword) ----
    {
        "title": "Burning smell near Line A gearbox",
        "description": "There's a faint burning-electrical smell coming from the Line A drive gearbox. It's still running normally for now, but the smell is new.",
        "location": "Line A - Drive Gearbox",
        "reported_by": "operator.j.rivera",
    },
    {
        "title": "Occasional loud bang from compressor",
        "description": "The compressor lets out a loud bang every so often, then keeps running. Air pressure is holding; nobody's sure if it's serious.",
        "location": "Utilities - Compressor Room",
        "reported_by": "operator.f.moreau",
    },
    {
        "title": "Robot drifting off pick point",
        "description": "The pick-and-place robot is landing slightly off the nest and occasionally clips the fixture. Still cycling; positional accuracy is degrading.",
        "location": "Assembly - Robot Cell 2",
        "reported_by": "operator.t.owusu",
    },
]


def seed_extra():
    init_db()
    db = SessionLocal()
    try:
        existing_titles = {t for (t,) in db.query(models.WorkOrder.title).all()}
        added = 0
        for order in EXTRA_ORDERS:
            if order["title"] in existing_titles:
                continue
            db.add(models.WorkOrder(status=models.STATUS_PENDING, **order))
            added += 1
        db.commit()
        skipped = len(EXTRA_ORDERS) - added
        print(f"Added {added} new work orders" + (f" (skipped {skipped} already present)." if skipped else "."))
    finally:
        db.close()


if __name__ == "__main__":
    seed_extra()
