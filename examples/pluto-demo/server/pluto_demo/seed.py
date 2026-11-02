"""The Halyard Robotics workspace: a fictional forty-person company, seeded as files.

Every document, sheet and note is a file in one namespace. The typed edges
between them are files too, which is what lets ``graph`` answer "what did
this decision touch". The finance folder is the governance moment: hidden
from everyone, granted to Clay by name.
"""

from __future__ import annotations

from typing import NamedTuple

from vfs.authority import Principal


class Person(NamedTuple):
    principal: Principal
    name: str
    role: str


PEOPLE: tuple[Person, ...] = (
    Person(Principal("clay"), "Clay Gendron", "Founder"),
    Person(Principal("sam"), "Sam Reyes", "Engineer, joined last week"),
)

AGENT = Principal("atlas", kind="service")
AGENT_NAME = "Atlas"
AGENT_ROLE = "Workspace agent"

RESTRICTED_PREFIX = "/finance"
RESTRICTED_GRANTS: tuple[tuple[str, str], ...] = (("clay", "read_write"),)


class Link(NamedTuple):
    source: str
    target: str
    edge_type: str


FILES: dict[str, str] = {
    "/docs/handbook.md": """# Halyard handbook

Halyard builds compliant grippers and actuators for warehouse robots. Forty people, two offices, one rule: ship what the field can trust.

## How we work

- Decisions are written down in `/meetings` on the day they are made, with the people who made them. A decision that is not written down did not happen.
- Specs live in `/product`. A spec is the source of truth once it says Accepted at the top.
- Customer notes live in `/customers`, one file per account. Write what they said, not what you hoped they said.
- Finance lives in `/finance` and is visible to the leadership group only.

## Your first week

1. Read the gripper firmware spec and the two meeting notes that produced it.
2. Pair with your onboarding buddy on one field ticket end to end.
3. Ship something small to staging by Friday. The release checklist is in `/docs/release-checklist.md`.

## Time off

Take it. Tell your lead a week ahead for anything over two days and put it on the shared calendar. See `/docs/time-off-policy.md` for the details.
""",
    "/docs/release-checklist.md": """# Release checklist

Accepted

Every firmware or software release goes through this list. The person cutting the release owns the list; nobody else can tick a box for them.

- Field regression suite green on the hardware-in-the-loop rig.
- Torque limits re-verified on the GX-2 gripper and the AX-40 actuator.
- Release notes written for customers in plain language, with the affected serial ranges named.
- Rollback path tested on one staging unit.
- Support team briefed one day before the release goes out.
""",
    "/docs/time-off-policy.md": """# Time off policy

Halyard does not count days. Take the time you need and keep your team informed.

- Under two days: tell your lead and mark the calendar.
- Two days or more: tell your lead a week ahead.
- Parental leave: sixteen weeks paid for every parent.
- Field engineers on a customer site swap with the on-call rota before they leave.
""",
    "/docs/engineering/firmware-conventions.md": """# Firmware conventions

The gripper and actuator firmware share one repository and one toolchain.

- Rust for the control loop, C only where a vendor SDK forces it.
- Every torque or velocity limit is a named constant in `limits.rs` with the test that proves it.
- A safety-relevant change ships with a field note in `/product` and a line in the release checklist.
- Firmware versions are dated: `2026.10.2` is the second release cut in October 2026.
""",
    "/meetings/2026-10-14-firmware-review.md": """# Firmware review, 14 October 2026

Present: Clay, Priya (firmware lead), Marco (field engineering), Dana (support).

## Gripper firmware

Priya walked through the GX-2 grip-force regression. Three customer units in the Tandem Logistics fleet overshot the configured grip force by up to 12% after the 2026.9.1 release. Root cause is the new force estimator trusting a stale encoder reading during a fast close.

## Decision

We decided to roll the GX-2 fleet back to firmware 2026.8.3 this week and to ship the fixed estimator as 2026.10.2 after a full week on the hardware-in-the-loop rig. Marco owns the rollback. Priya owns 2026.10.2. The estimator fix is specified in the gripper firmware spec.

## Actions

- Marco: roll back every GX-2 at Tandem Logistics and Bellweather Fulfilment by 18 October.
- Priya: land the estimator fix and start the rig soak on 15 October.
- Dana: brief the three affected customers today.
""",
    "/meetings/2026-10-21-leadership.md": """# Leadership meeting, 21 October 2026

Present: Clay, Priya, Marco, Dana, Jun (finance).

## Actuator recall

The AX-40 actuator seal issue is now a recall. Jun walked through the cost: about 310k across the 1,900 affected units, booked against Q4. Marco's team will swap seals on site rather than ship units back. Customers with AX-40 units built before August 2026 are affected; the list is in the recall notice in `/product`.

## Hiring

Sam Reyes starts on 27 October on the firmware team. Priya is the onboarding buddy.

## Decision

We decided to fund the recall from the operating budget instead of raising the bridge early. Jun will update the runway model and the board update. We revisit the bridge in the December board meeting.
""",
    "/meetings/2026-10-28-product-sync.md": """# Product sync, 28 October 2026

Present: Priya, Marco, Sam, Dana.

## 2026.10.2 status

The estimator fix has been on the rig for nine days with no overshoot above 1%. Priya proposes cutting 2026.10.2 on 30 October and rolling it to Tandem Logistics first, then Bellweather Fulfilment.

## Decision

Agreed: cut 2026.10.2 on 30 October. Sam pairs with Priya on the release checklist as the first-week ticket.

## Field notes

Marco: the AX-40 seal swaps are 40% done. Northgate Grocery asked whether their newer units are affected; they are not, their units were built in September.
""",
    "/product/gripper-firmware-spec.md": """# Gripper firmware spec

Accepted

The GX-2 gripper firmware controls grip force, close speed and the safety envelope for a two-finger parallel gripper rated to 180 N.

## Force estimator

The force estimator fuses the motor current with the finger encoder. From 2026.10.2 the estimator rejects any encoder sample older than 2 ms during a close faster than 40 mm/s; a stale sample previously let the estimate lag the real force, which is how the 2026.9.1 overshoot happened.

## Limits

- Maximum grip force: 180 N, enforced in hardware and in `limits.rs`.
- Maximum close speed: 120 mm/s.
- Overshoot tolerance for release: 2% over the configured force on the hardware-in-the-loop rig.

## Release plan

2026.10.2 goes to Tandem Logistics first, then Bellweather Fulfilment, then the rest of the fleet. The rollback target stays 2026.8.3 until two weeks after the last unit is updated.
""",
    "/product/ax40-recall-notice.md": """# AX-40 actuator recall notice

Status: active, opened 21 October 2026

A batch of AX-40 actuators built before 1 August 2026 shipped with a shaft seal that can weep lubricant after about 400 hours of duty. The seal is replaced on site by a Halyard field engineer in about twenty minutes per unit.

## Affected serial ranges

AX40-24-00001 through AX40-26-07980.

## Affected customers

- Tandem Logistics: 1,100 units across two sites.
- Bellweather Fulfilment: 620 units.
- Orinoco Parcel: 180 units.

Northgate Grocery is not affected; their units were built in September 2026.

## What customers need to do

Nothing. Field engineering schedules the swap with each site. Units keep running until the swap; a weeping seal is a maintenance issue, not a safety one.
""",
    "/product/roadmap-2027.md": """# Roadmap 2027

Draft

- Q1: GX-3 gripper with a 250 N rating and a vision-guided close.
- Q2: AX-50 actuator with a sealed-for-life shaft.
- Q3: Fleet console, one screen for every unit a customer runs, with firmware rollout by site.
- Q4: Third-party integrator program.
""",
    "/customers/tandem-logistics.md": """# Tandem Logistics

Largest account. Two sites near Columbus, 1,100 AX-40 actuators and 340 GX-2 grippers.

## Recent

- 14 October: three GX-2 units overshot grip force after 2026.9.1. Rolled back to 2026.8.3 on 16 October. They were calm about it and asked for the fix timeline in writing.
- 21 October: told them about the AX-40 recall. Seal swaps started 23 October, site one first.
- They want the fleet console on the 2027 roadmap badly. Their ops lead would pilot it.
""",
    "/customers/bellweather-fulfilment.md": """# Bellweather Fulfilment

Second account by units. One site in Reno, 620 AX-40 actuators and 120 GX-2 grippers.

## Recent

- Rolled GX-2 back to 2026.8.3 on 17 October as a precaution; none of their units overshot.
- AX-40 seal swaps scheduled for the first two weeks of November.
- Renewal conversation opens in January. They asked whether a volume discount applies above 1,000 units.
""",
    "/customers/orinoco-parcel.md": """# Orinoco Parcel

Pilot account. 180 AX-40 actuators on a sorting line in Memphis.

## Recent

- Affected by the AX-40 recall. Swaps scheduled for 12 November.
- The pilot converts to a full contract if uptime stays above 99.5% through December.
""",
    "/customers/northgate-grocery.md": """# Northgate Grocery

New account, signed September 2026. 90 AX-40 actuators built in September, so not part of the recall.

## Recent

- Asked on 28 October whether they are affected by the recall. Marco confirmed they are not.
- Interested in the GX-3 for produce handling.
""",
    "/finance/board-update-2026-10.md": """# Board update, October 2026

Confidential. Leadership group only.

## Cash and runway

Cash at end of October is 4.1M. Net burn for October was 290k, up from 240k because of the first AX-40 recall costs. At the planned burn of 310k a month, runway is about thirteen months, to the end of November 2027.

## Decision this month

We are funding the AX-40 recall, about 310k in total, from the operating budget. We decided against raising the bridge early; we revisit it at the December board meeting with the recall behind us.

## Revenue

Annual recurring revenue is 3.4M. Tandem Logistics renewed in September at 1.6M. Bellweather Fulfilment's renewal opens in January.
""",
    "/finance/runway-model.csv": """month,cash_start,revenue,burn,cash_end
2026-10,4390000,283000,290000,4100000
2026-11,4100000,283000,310000,3790000
2026-12,3790000,283000,310000,3480000
2027-01,3480000,290000,310000,3170000
2027-02,3170000,290000,310000,2860000
2027-03,2860000,290000,300000,2560000
""",
    "/finance/vendor-payments-2026-10.csv": """vendor,amount,category
Columbus Seal Supply,84000,recall
Field travel,22000,recall
Cloud,31000,infrastructure
Payroll,410000,people
""",
    "/people/onboarding-buddies.md": """# Onboarding buddies

| New hire | Buddy | Start |
| --- | --- | --- |
| Sam Reyes | Priya | 27 October 2026 |
| Lena Okafor | Marco | 10 November 2026 |
""",
}

LINKS: tuple[Link, ...] = (
    Link("/meetings/2026-10-14-firmware-review.md", "/product/gripper-firmware-spec.md", "decides"),
    Link("/meetings/2026-10-28-product-sync.md", "/product/gripper-firmware-spec.md", "decides"),
    Link("/meetings/2026-10-14-firmware-review.md", "/customers/tandem-logistics.md", "mentions"),
    Link("/meetings/2026-10-14-firmware-review.md", "/customers/bellweather-fulfilment.md", "mentions"),
    Link("/meetings/2026-10-21-leadership.md", "/product/ax40-recall-notice.md", "decides"),
    Link("/meetings/2026-10-21-leadership.md", "/finance/board-update-2026-10.md", "informs"),
    Link("/product/ax40-recall-notice.md", "/customers/tandem-logistics.md", "affects"),
    Link("/product/ax40-recall-notice.md", "/customers/bellweather-fulfilment.md", "affects"),
    Link("/product/ax40-recall-notice.md", "/customers/orinoco-parcel.md", "affects"),
    Link("/finance/board-update-2026-10.md", "/finance/runway-model.csv", "references"),
    Link("/docs/handbook.md", "/docs/release-checklist.md", "references"),
    Link("/docs/handbook.md", "/docs/time-off-policy.md", "references"),
    Link("/docs/handbook.md", "/product/gripper-firmware-spec.md", "references"),
    Link("/people/onboarding-buddies.md", "/meetings/2026-10-21-leadership.md", "references"),
)
