# 02 — Milestones

The 8 phases in `01_roadmap.md` grouped into 4 checkpoints, each answering one specific question the thesis
needs answered. The Gantt chart's five `crit` markers are **real deadlines** from the department syllabus
(`2302493/499`, academic year 2569/2026) — not estimates; the phase bars around them are a proposed pace.

| Milestone | Phases | Answers | Done when | Status |
|---|---|---|---|---|
| **M1 — Detection proven** | P0, P1 | Can a classical (non-ML) pipeline find and track the interface reliably? | P1 gate closed (`P1-08`) | In progress — P0 done, P1's only remaining item is `P1-08` |
| **M2 — Volume + hardware ready** | P2, P3 | Can height convert to volume, and can the pump be driven safely? | P2 and P3 gates both closed | In progress — P2 done, P3 not started |
| **M3 — Closed loop validated** | P4, P5 | Does the whole system work unattended, repeatably, on the final target pair (water-oil)? | P5 gate closed (10-run RMSE) | Not started |
| **M4 — Report** | P7 | Is it written up? | Report submitted | Not started |

```mermaid
gantt
    title extractlab timeline — anchored to the 2302493/2302499 syllabus
    dateFormat YYYY-MM-DD
    axisFormat %b %Y

    section Fixed deadlines (syllabus, not estimates)
    Safety cert exam, 20% of 2302493        :crit, milestone, dl1, 2026-09-30, 0d
    Progress report, P ภาคต้น (SP_CH_S4)     :crit, milestone, dl2, 2026-11-27, 0d
    Full report due, 20% of 2302499         :crit, milestone, dl3, 2027-04-23, 0d
    Oral + poster exhibition, 30%           :crit, milestone, dl4, 2027-05-13, 0d
    Final complete report                   :crit, milestone, dl5, 2027-05-18, 0d

    section M1 - detection proven (estimated)
    P1-08 confirm live                      :active, p1, 2026-10-08, 10d

    section M2 - volume + hardware ready
    P2-02..04 measure, fit, verify          :done, p2, 2026-10-16, 1d
    P3-01..06 motor driver + pump.py        :p3, after p1, 25d

    section M3 - closed loop validated (estimated)
    P4-01..05 combine + dry run             :p4, 2027-01-05, 26d
    P5-01..03 10-run RMSE                   :p5, after p4, 26d

    section M4 - report (estimated)
    Draft report                            :p7, after p5, 40d
    Rehearse presentation                   :p7b, 2027-05-01, 12d
```

This lands M1 (detection proven) well before the 27 Nov progress-report checkpoint, and M4 (report draft) before
the 23 Apr full-report deadline, with slack before the 13 May presentation. Only the five `crit` dates are
commitments — adjust the phase bars freely as the actual pace becomes clearer.
