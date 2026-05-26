from datetime import datetime
from pathlib import Path

from membership_reader import (
    ClientAggregate,
    MemberAggregates,
    SegmentBreakdown,
    read_client_aggregates,
    read_membership,
)
from output_paths import ANNUAL_DIR, ANOMALIES_DIR, BRIEFS_DIR
from pnl_reader import read_pnl

ALL_OUTPUT_DIRS = [BRIEFS_DIR, ANOMALIES_DIR, ANNUAL_DIR]


def _format_raw_pnl(months) -> str:
    lines = ["## RAW MONTHLY P&L (from ABC Master sample.xlsx, all values in INR)\n"]
    lines.append("| Month | Ultra Rev | Premium Rev | Total Rev | Total Exp | Profit | GM% |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for m in months:
        lines.append(f"| {m.label} | {m.ultra_rev:,.0f} | {m.premium_rev:,.0f} | "
                     f"{m.total_rev:,.0f} | {m.total_exp:,.0f} | {m.profit:,.0f} | {m.gm_pct*100:.1f}% |")
    lines.append("")
    lines.append("## EXPENSE LINE-ITEM DETAIL (per month, INR)\n")
    lines.append("| Month | Salary | Electricity | Repair | Grocery | Mandir | Paytm | Misc | Diesel |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for m in months:
        lines.append(f"| {m.label} | {m.salary:,.0f} | {m.electricity:,.0f} | {m.repair:,.0f} | "
                     f"{m.grocery:,.0f} | {m.mandir:,.0f} | {m.paytm:,.0f} | {m.misc:,.0f} | {m.diesel:,.0f} |")
    return "\n".join(lines)


def _format_membership(agg: MemberAggregates) -> str:
    lines = ["## MEMBERSHIP DATA (from Membership Summary + Ultra + Premium tabs)\n"]

    lines.append("### FY2025-26 totals by fitness centre type\n")
    lines.append("| Fitness Centre Type | Total Members | Active | Total Revenue | Avg Rev / Member |")
    lines.append("|---|---:|---:|---:|---:|")
    for t in ("Ultra", "Premium"):
        lines.append(f"| {t} | {agg.total_members.get(t, 0)} | {agg.total_active.get(t, 0)} | "
                     f"INR {agg.total_revenue.get(t, 0):,.0f} | INR {agg.avg_rev_per_member.get(t, 0):,.0f} |")

    lines.append("")
    lines.append("### Total transactions tagged New vs Existing, by fitness centre type (FY2025-26)\n")
    lines.append("**Important:** these are TRANSACTION counts, not unique-member counts. A single member can appear as 'New' in their first month and 'Existing' in renewal months. For unique-member totals see the next section.\n")
    lines.append("| Fitness Centre Type | New Transactions | Existing Transactions | New Revenue | Existing Revenue |")
    lines.append("|---|---:|---:|---:|---:|")
    for t in ("Ultra", "Premium"):
        lines.append(f"| {t} | {agg.new_count_by_type.get(t, 0)} | {agg.existing_count_by_type.get(t, 0)} | "
                     f"INR {agg.new_rev_by_type.get(t, 0):,.0f} | INR {agg.existing_rev_by_type.get(t, 0):,.0f} |")

    lines.append("")
    lines.append("### Overall New vs Existing (Ultra + Premium combined, unique members, per Membership Summary tab)\n")
    lines.append(f"- **Existing:** {agg.overall_existing_members} unique members, INR {agg.overall_existing_revenue:,.0f} revenue")
    lines.append(f"- **New:** {agg.overall_new_members} unique members, INR {agg.overall_new_revenue:,.0f} revenue")
    total_unique = agg.overall_existing_members + agg.overall_new_members
    if total_unique:
        lines.append(f"- **Total unique members across FY:** {total_unique}")

    lines.append("")
    lines.append("### Monthly NEW CLIENT signups by fitness centre type (count and revenue)\n")
    all_months = set()
    for t in ("Ultra", "Premium"):
        all_months.update(agg.monthly_new_count.get(t, {}).keys())
        all_months.update(agg.monthly_existing_count.get(t, {}).keys())
    sorted_months = sorted(all_months, key=lambda s: datetime.strptime(s, "%b %Y"))

    lines.append("| Month | Ultra New (count) | Ultra New Rev | Premium New (count) | Premium New Rev |")
    lines.append("|---|---:|---:|---:|---:|")
    for m in sorted_months:
        un = agg.monthly_new_count.get("Ultra", {}).get(m, 0)
        ur = agg.monthly_new_revenue.get("Ultra", {}).get(m, 0)
        pn = agg.monthly_new_count.get("Premium", {}).get(m, 0)
        pr = agg.monthly_new_revenue.get("Premium", {}).get(m, 0)
        lines.append(f"| {m} | {un} | INR {ur:,.0f} | {pn} | INR {pr:,.0f} |")

    lines.append("")
    lines.append("### Monthly EXISTING CLIENT transactions by fitness centre type (count and revenue)\n")
    lines.append("| Month | Ultra Existing (count) | Ultra Existing Rev | Premium Existing (count) | Premium Existing Rev |")
    lines.append("|---|---:|---:|---:|---:|")
    for m in sorted_months:
        un = agg.monthly_existing_count.get("Ultra", {}).get(m, 0)
        ur = agg.monthly_existing_revenue.get("Ultra", {}).get(m, 0)
        pn = agg.monthly_existing_count.get("Premium", {}).get(m, 0)
        pr = agg.monthly_existing_revenue.get("Premium", {}).get(m, 0)
        lines.append(f"| {m} | {un} | INR {ur:,.0f} | {pn} | INR {pr:,.0f} |")

    return "\n".join(lines)


def _format_client_aggregates(clients: dict[str, ClientAggregate], seg: SegmentBreakdown, top_n: int = 25) -> str:
    lines = ["## CLIENT-LEVEL DATA (aggregated from Ultra + Premium raw transaction rows)\n"]
    lines.append(f"Total unique client-records: {len(clients)} (a client appears once per fitness centre type they belong to)\n")

    for gym_type in ("Ultra", "Premium"):
        type_clients = [c for c in clients.values() if c.gym_type == gym_type]
        if not type_clients:
            continue

        lines.append(f"\n### Top {top_n} {gym_type} clients by TOTAL PAID (FY2025-26)\n")
        lines.append("| Rank | Client Name | Transactions | Total Paid | Cash | Online | Discount | Location(s) |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---|")
        ranked = sorted(type_clients, key=lambda c: c.total_paid, reverse=True)[:top_n]
        for i, c in enumerate(ranked, 1):
            locs = ", ".join(sorted(c.locations)) or "(unspecified)"
            lines.append(f"| {i} | {c.name} | {c.transaction_count} | INR {c.total_paid:,.0f} | "
                         f"INR {c.cash_paid:,.0f} | INR {c.online_paid:,.0f} | INR {c.discount_given:,.0f} | {locs} |")

        lines.append(f"\n### Top {top_n} {gym_type} clients by TRANSACTION COUNT (most frequent)\n")
        lines.append("| Rank | Client Name | Transactions | Total Paid | First Seen | Last Seen |")
        lines.append("|---|---|---:|---:|---|---|")
        ranked = sorted(type_clients, key=lambda c: c.transaction_count, reverse=True)[:top_n]
        for i, c in enumerate(ranked, 1):
            fs = c.first_seen.strftime("%d-%b-%Y") if c.first_seen else "—"
            ls = c.last_seen.strftime("%d-%b-%Y") if c.last_seen else "—"
            lines.append(f"| {i} | {c.name} | {c.transaction_count} | INR {c.total_paid:,.0f} | {fs} | {ls} |")

    # Outstanding balance
    outstanding = sorted(
        (c for c in clients.values() if c.outstanding > 0),
        key=lambda c: c.outstanding, reverse=True,
    )
    if outstanding:
        lines.append(f"\n### Clients with OUTSTANDING BALANCE ({len(outstanding)} total)\n")
        lines.append("| Client Name | Fitness Centre Type | Outstanding | Last Seen |")
        lines.append("|---|---|---:|---|")
        for c in outstanding[:30]:
            ls = c.last_seen.strftime("%d-%b-%Y") if c.last_seen else "—"
            lines.append(f"| {c.name} | {c.gym_type} | INR {c.outstanding:,.0f} | {ls} |")

    # Refunds
    refunded = sorted(
        (c for c in clients.values() if c.refund > 0),
        key=lambda c: c.refund, reverse=True,
    )
    if refunded:
        lines.append(f"\n### Clients with REFUNDS issued ({len(refunded)} total)\n")
        lines.append("| Client Name | Fitness Centre Type | Refund Amount |")
        lines.append("|---|---|---:|")
        for c in refunded[:30]:
            lines.append(f"| {c.name} | {c.gym_type} | INR {c.refund:,.0f} |")

    # Discounts
    discounted = sorted(
        (c for c in clients.values() if c.discount_given > 0),
        key=lambda c: c.discount_given, reverse=True,
    )
    if discounted:
        lines.append(f"\n### Top 30 clients by DISCOUNT received\n")
        lines.append("| Client Name | Fitness Centre Type | Discount Total |")
        lines.append("|---|---|---:|")
        for c in discounted[:30]:
            lines.append(f"| {c.name} | {c.gym_type} | INR {c.discount_given:,.0f} |")
        total_disc = sum(c.discount_given for c in clients.values())
        lines.append(f"\n_Total discounts across all clients: INR {total_disc:,.0f}_")

    # Segment breakdowns
    lines.append("\n### Revenue by PAYMENT MODE (Cash vs Online vs Other)\n")
    lines.append("| Fitness Centre Type | Mode | Revenue |")
    lines.append("|---|---|---:|")
    for gym_type in ("Ultra", "Premium"):
        modes = seg.by_payment_mode.get(gym_type, {})
        for mode, rev in sorted(modes.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"| {gym_type} | {mode} | INR {rev:,.0f} |")

    lines.append("\n### Revenue by MEMBERSHIP DURATION\n")
    lines.append("| Fitness Centre Type | Duration | Revenue |")
    lines.append("|---|---|---:|")
    for gym_type in ("Ultra", "Premium"):
        mtypes = seg.by_membership_type.get(gym_type, {})
        for mt, rev in sorted(mtypes.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"| {gym_type} | {mt} | INR {rev:,.0f} |")

    lines.append("\n### Revenue by LOCATION\n")
    lines.append("| Fitness Centre Type | Location | Revenue |")
    lines.append("|---|---|---:|")
    for gym_type in ("Ultra", "Premium"):
        locs = seg.by_location.get(gym_type, {})
        for loc, rev in sorted(locs.items(), key=lambda x: x[1], reverse=True)[:15]:
            lines.append(f"| {gym_type} | {loc} | INR {rev:,.0f} |")

    if seg.pt_clients:
        lines.append(f"\n### PT (Personal Training) clients ({len(seg.pt_clients)} total)\n")
        lines.append("| Client Name | Fitness Centre Type | Transactions | Total Paid |")
        lines.append("|---|---|---:|---:|")
        for c in seg.pt_clients[:30]:
            lines.append(f"| {c.name} | {c.gym_type} | {c.transaction_count} | INR {c.total_paid:,.0f} |")

    return "\n".join(lines)


def _collect_brief_files() -> list[Path]:
    files: list[Path] = []
    for d in ALL_OUTPUT_DIRS:
        if d.exists():
            files.extend(sorted(d.glob("*.md")))
    return files


def _format_briefs() -> str:
    files = _collect_brief_files()
    if not files:
        return "## EXISTING BRIEFS & REPORTS\n\n(None generated yet — run narrate_month.py / narrate_year.py / sentinel.py first.)"
    sections = [f"## EXISTING BRIEFS & REPORTS ({len(files)} files across 3 folders)\n"]
    for f in files:
        sections.append(f"\n### File: {f.parent.name}\\{f.name}\n")
        sections.append(f.read_text(encoding="utf-8"))
    return "\n".join(sections)


def build_full_context() -> tuple[str, dict]:
    months = read_pnl()
    membership = read_membership()
    clients, segments = read_client_aggregates()
    raw_section = _format_raw_pnl(months)
    membership_section = _format_membership(membership)
    clients_section = _format_client_aggregates(clients, segments)
    briefs_section = _format_briefs()
    briefs_files = _collect_brief_files()
    context = (
        "# DATA AVAILABLE TO YOU\n\n"
        f"{raw_section}\n\n{membership_section}\n\n{clients_section}\n\n{briefs_section}\n"
    )
    meta = {
        "months": len(months),
        "first_month": months[0].label if months else "n/a",
        "last_month": months[-1].label if months else "n/a",
        "briefs_count": len(briefs_files),
        "briefs_filenames": [f.name for f in briefs_files],
        "unique_clients": len(clients),
        "pt_clients": len(segments.pt_clients),
        "context_chars": len(context),
        "total_members_ultra": membership.total_members.get("Ultra", 0),
        "total_members_premium": membership.total_members.get("Premium", 0),
    }
    return context, meta
