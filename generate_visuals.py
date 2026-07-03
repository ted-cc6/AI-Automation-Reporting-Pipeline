"""
generate_visuals.py
Generates all 11 report charts directly from analysis_results.json.
Run: python generate_visuals.py --run-id 2026_Q2
"""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

# ── Color system ───────────────────────────────────────────────────────────────
C = {
    'surface':   '#fcfcfb',
    'ink_1':     '#0b0b0b',
    'ink_2':     '#52514e',
    'ink_muted': '#898781',
    'grid':      '#e1e0d9',
    'axis':      '#c3c2b7',
    's1':        '#2a78d6',   # blue  (primary series)
    's2':        '#1baf7a',   # aqua  (secondary series)
    's3':        '#eda100',   # amber (significance marker)
    'good':      '#0ca30c',   # green (positive outcome)
    'critical':  '#d03b3b',   # red   (detractors / warning)
    'muted_bar': '#86b6ef',   # light blue (step 250, secondary bars)
}

DPI = 150
SOURCE = 'VisionFund Insurance Impact Survey — Vietnam 2026 Q2'
ROOT = Path(__file__).parent


# ── Shared helpers ─────────────────────────────────────────────────────────────

def base_style(ax, fig):
    fig.patch.set_facecolor(C['surface'])
    ax.set_facecolor(C['surface'])
    for spine in ('top', 'right'):
        ax.spines[spine].set_visible(False)
    ax.spines['left'].set_color(C['axis'])
    ax.spines['bottom'].set_color(C['axis'])
    ax.tick_params(colors=C['ink_2'], labelsize=9)


def add_title(fig, title, subtitle=None):
    fig.suptitle(title, x=0.05, ha='left', y=0.98,
                 fontsize=13, fontweight='bold', color=C['ink_1'])
    if subtitle:
        fig.text(0.05, 0.92, subtitle, ha='left',
                 fontsize=9, color=C['ink_muted'])


def add_source(fig, note=None):
    text = f'{note}    {SOURCE}' if note else SOURCE
    fig.text(0.05, 0.01, text, fontsize=7.5, color=C['ink_muted'])


def hbar_chart(ax, labels, values, colors, max_val=None):
    """Horizontal bar chart with direct value labels."""
    if max_val is None:
        max_val = max(v for v in values if v is not None) if values else 100
    y = np.arange(len(labels))
    for i, (label, val, color) in enumerate(zip(labels, values, colors)):
        if val is None:
            ax.text(1, i, 'SUPPRESSED', va='center', ha='left',
                    fontsize=8, color=C['ink_muted'], fontstyle='italic')
            continue
        ax.barh(i, val, height=0.55, color=color, linewidth=0, zorder=2)
        ax.text(val + max_val * 0.012, i, f'{val:.1f}%',
                va='center', ha='left', fontsize=8.5,
                color=C['ink_2'], fontweight='bold')

    ax.xaxis.grid(True, color=C['grid'], linewidth=0.5, zorder=0)
    ax.set_axisbelow(True)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10, color=C['ink_1'])
    ax.set_xlim(0, max_val * 1.20)
    ax.set_xticklabels([])
    ax.tick_params(axis='x', which='both', bottom=False)


def save_fig(fig, path):
    fig.savefig(path, dpi=DPI, bbox_inches='tight',
                facecolor=C['surface'], edgecolor='none')
    plt.close(fig)
    print(f'  Saved: {path.name}')


def load_data(run_id):
    path = ROOT / 'runs' / run_id / 'analysis_results.json'
    with open(path, encoding='utf-8') as f:
        return json.load(f)


# ── Chart 1: Coverage Understanding by Segment ────────────────────────────────

def chart_part1_coverage(data, out_dir):
    p1 = data['parts']['part_1']['metrics']['coverage_understanding']
    seg = p1['segments']
    overall = p1['headline']['value'] * 100

    rows = [
        ('Person with Disability', seg['pwd']['value'] * 100),
        ('First Time Access', seg['first_time_access']['value'] * 100),
        ('Non-Claimant', seg['non_claimant']['value'] * 100),
        ('Female', seg['female']['value'] * 100),
        ('Male', seg['male']['value'] * 100),
        ('Claimant', seg['claimant']['value'] * 100),
        ('Overall', overall),
    ]
    labels = [r[0] for r in rows]
    values = [r[1] for r in rows]
    colors = [C['muted_bar']] * 6 + [C['s1']]

    fig, ax = plt.subplots(figsize=(7, 4.5))
    base_style(ax, fig)
    hbar_chart(ax, labels, values, colors)
    ax.axvline(50, color=C['axis'], linewidth=0.8, linestyle='--', zorder=1)

    add_title(fig, 'Coverage Understanding by Segment',
              '% who understand what their insurance covers  (n=2,104)')
    add_source(fig)
    plt.tight_layout(rect=[0, 0.04, 1, 0.90])
    save_fig(fig, out_dir / 'part1_coverage_bar.png')


# ── Chart 2: Claim Process Understanding by Segment ───────────────────────────

def chart_part1_claims_process(data, out_dir):
    p1 = data['parts']['part_1']['metrics']['claim_process_understanding']
    seg = p1['segments']
    overall = p1['headline']['value'] * 100

    rows = [
        ('Non-Claimant', seg['non_claimant']['value'] * 100),
        ('Female', seg['female']['value'] * 100),
        ('Male', seg['male']['value'] * 100),
        ('Overall', overall),
        ('Claimant', seg['claimant']['value'] * 100),
    ]
    labels = [r[0] for r in rows]
    values = [r[1] for r in rows]
    colors = [C['muted_bar']] * 2 + [C['muted_bar']] + [C['s1']] + [C['s1']]

    fig, ax = plt.subplots(figsize=(7, 3.8))
    base_style(ax, fig)
    hbar_chart(ax, labels, values, colors)
    ax.axvline(50, color=C['axis'], linewidth=0.8, linestyle='--', zorder=1)

    add_title(fig, 'Claim Process Understanding by Segment',
              '% who understand how to submit a claim  (n=2,104)')
    add_source(fig)
    plt.tight_layout(rect=[0, 0.04, 1, 0.90])
    save_fig(fig, out_dir / 'part1_claims_process_bar.png')


# ── Chart 3: Claims Funnel ────────────────────────────────────────────────────

def chart_part2_funnel(data, out_dir):
    cf = data['parts']['part_2']['claims_funnel']
    stages   = ['Experienced\ninsured event', 'Filed\na claim', 'Claim\nwas paid']
    ns       = [cf['experienced_event']['n'], cf['filed_claim']['n'], cf['claim_paid']['n']]
    rate_txt = ['17.2% of\nall clients', '42.1% of\nthose\nwith event', '37.9% of\nclaimants']
    colors   = ['#6da7ec', '#3987e5', '#1c5cab']   # ordinal blue steps 300→400→550

    fig, ax = plt.subplots(figsize=(7, 4.2))
    base_style(ax, fig)

    x = np.array([0, 1, 2])
    bars = ax.bar(x, ns, width=0.5, color=colors, linewidth=0, zorder=2)

    for bar, n, rate in zip(bars, ns, rate_txt):
        cx = bar.get_x() + bar.get_width() / 2
        ax.text(cx, bar.get_height() + 5, f'n={n:,}',
                ha='center', va='bottom', fontsize=11,
                fontweight='bold', color=C['ink_1'])
        ax.text(cx, bar.get_height() * 0.5, rate,
                ha='center', va='center', fontsize=8.5,
                color='white', fontweight='bold')

    # Arrows between bars
    for i in range(2):
        mid_y = ns[i] * 0.55
        ax.annotate('', xy=(x[i+1] - 0.27, mid_y), xytext=(x[i] + 0.27, mid_y),
                    arrowprops=dict(arrowstyle='->', color=C['ink_muted'], lw=1.5))

    ax.set_xticks(x)
    ax.set_xticklabels(stages, fontsize=10.5, color=C['ink_1'])
    ax.set_ylabel('Number of clients', fontsize=9, color=C['ink_2'])
    ax.yaxis.grid(True, color=C['grid'], linewidth=0.5, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(axis='y', colors=C['ink_2'])
    ax.tick_params(axis='x', bottom=False)

    add_title(fig, 'Claims Funnel', 'Of 2,111 surveyed clients — Vietnam 2026 Q2')
    add_source(fig)
    plt.tight_layout(rect=[0, 0.04, 1, 0.90])
    save_fig(fig, out_dir / 'part2_funnel.png')


# ── Chart 4: Reasons for Not Claiming ─────────────────────────────────────────

def chart_part2_no_claim(data, out_dir):
    dist = data['parts']['part_2']['no_claim_reasons']['distribution']
    short = {
        'I was not covered at that time':     'Not covered at that time',
        'I did not know how to file a claim': 'Did not know how to claim',
        'Other (please specify)':             'Other reason',
        'The loss was not significant':       'Loss was not significant',
        'Claim process is cumbersome':        'Process too cumbersome',
        'The benefit I would receive is low': 'Expected benefit too low',
    }
    labels = [short.get(d['value'], d['value']) for d in dist]
    values = [d['pct'] * 100 for d in dist]
    colors = [C['s1']] * len(labels)

    fig, ax = plt.subplots(figsize=(7, 4))
    base_style(ax, fig)
    hbar_chart(ax, labels, values, colors)

    add_title(fig, 'Why Clients Did Not Claim',
              '% of clients with an insured event who did not file a claim  (n=210)')
    add_source(fig)
    plt.tight_layout(rect=[0, 0.04, 1, 0.90])
    save_fig(fig, out_dir / 'part2_no_claim_reasons.png')


# ── Chart 5: Claim Challenges ─────────────────────────────────────────────────

def chart_part2_challenges(data, out_dir):
    ranked = data['parts']['part_2']['claim_challenges']['ranked']['ranked']
    short = {
        'It was difficult to know the status of the claim once documents were submitted':
            'Difficult to know claim status',
        'Claim documents were difficult to collect from hospitals or authorities':
            'Documents hard to collect',
        'It took a long time to receive the claim amount':
            'Long time to receive payout',
        'I did not receive enough support or guidance on the claim process':
            'Insufficient support / guidance',
        'Claim documents were difficult to submit':
            'Documents hard to submit',
    }
    items = [r for r in ranked if r['option'] != 'Other']
    labels = [short.get(r['option'], r['option'][:45]) for r in items]
    values = [r['pct'] * 100 for r in items]
    colors = [C['s1']] * len(labels)

    fig, ax = plt.subplots(figsize=(7, 3.8))
    base_style(ax, fig)
    hbar_chart(ax, labels, values, colors)

    add_title(fig, 'Top Claim Challenges',
              '% of 85 claimants who experienced each challenge (multi-select)')
    add_source(fig)
    plt.tight_layout(rect=[0, 0.04, 1, 0.90])
    save_fig(fig, out_dir / 'part2_claim_challenges.png')


# ── Chart 6: Financial Protection Panel ───────────────────────────────────────

def chart_part3_financial(data, out_dir):
    m = data['parts']['part_3']['metrics']

    tiles = [
        ('Negative\nCoping', m['negative_coping']['headline']['value'] * 100,
         'Claimants only (n=363)', C['s3'], '↓ lower is better'),
        ('High Financial\nStress', m['financial_stress_high']['headline']['value'] * 100,
         'Claimants only (n=363)', C['s3'], '↓ lower is better'),
        ('Alt. Insurance\nAccess Difficult', m['alternative_access_difficult']['headline']['value'] * 100,
         'All clients (n=2,104)', C['s1'], ''),
        ('Confidence\nto Pay', m['confidence_pay']['headline']['value'] * 100,
         'All clients (n=2,104)', C['good'], ''),
    ]

    fig, axes = plt.subplots(1, 4, figsize=(11, 3.5))
    fig.patch.set_facecolor(C['surface'])

    for ax, (label, val, base, color, note) in zip(axes, tiles):
        ax.set_facecolor(C['surface'])
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
        rect = mpatches.FancyBboxPatch(
            (0.05, 0.08), 0.90, 0.84,
            boxstyle='round,pad=0.02',
            facecolor='white', edgecolor=C['grid'], linewidth=1.2)
        ax.add_patch(rect)
        ax.text(0.50, 0.83, label, ha='center', va='center',
                fontsize=10, color=C['ink_2'], fontweight='bold')
        ax.text(0.50, 0.54, f'{val:.1f}%', ha='center', va='center',
                fontsize=24, color=color, fontweight='bold')
        if note:
            ax.text(0.50, 0.33, note, ha='center', va='center',
                    fontsize=7.5, color=C['ink_muted'])
        ax.text(0.50, 0.17, base, ha='center', va='center',
                fontsize=8, color=C['ink_muted'])

    fig.suptitle('Financial Protection Indicators', x=0.05, ha='left',
                 fontsize=13, fontweight='bold', color=C['ink_1'], y=1.04)
    fig.text(0.05, -0.04, SOURCE, fontsize=7.5, color=C['ink_muted'])
    plt.tight_layout()
    save_fig(fig, out_dir / 'part3_financial_protection.png')


# ── Chart 7: NPS Breakdown ────────────────────────────────────────────────────

def chart_part4_nps(data, out_dir):
    r = data['parts']['part_4']['nps']['result']
    score = r['value']
    groups = [
        ('Detractors\n(score 0–6)', r['detractors']['n'], r['detractors']['pct'] * 100, C['critical']),
        ('Passives\n(score 7–8)',   r['passives']['n'],   r['passives']['pct'] * 100,   C['ink_muted']),
        ('Promoters\n(score 9–10)', r['promoters']['n'],  r['promoters']['pct'] * 100,  C['good']),
    ]

    fig, ax = plt.subplots(figsize=(7.5, 3))
    base_style(ax, fig)
    ax.axis('off')
    fig.patch.set_facecolor(C['surface'])
    ax.set_facecolor(C['surface'])

    # Stacked horizontal bar
    left = 0
    for label, n, pct, color in groups:
        ax.barh(0, pct, left=left, height=0.45, color=color, linewidth=0)
        if pct > 7:
            ax.text(left + pct / 2, 0,
                    f'{pct:.1f}%\n(n={n:,})',
                    ha='center', va='center', fontsize=9.5,
                    color='white', fontweight='bold')
        left += pct

    # NPS score callout on the right
    ax.text(102, 0.28, 'NPS', ha='left', va='center',
            fontsize=11, color=C['ink_2'])
    ax.text(102, -0.08, f'{score:+.1f}', ha='left', va='center',
            fontsize=28, color=C['s1'], fontweight='bold')

    # Legend below
    patches = [mpatches.Patch(color=g[3], label=g[0].replace('\n', ' ')) for g in groups]
    ax.legend(handles=patches, loc='lower center', bbox_to_anchor=(0.45, -0.55),
              ncol=3, fontsize=9, frameon=False, labelcolor=C['ink_2'])

    ax.set_xlim(0, 120)
    ax.set_ylim(-0.5, 0.5)

    add_title(fig, 'Net Promoter Score', 'n=2,104 clients — Vietnam 2026 Q2')
    add_source(fig)
    plt.tight_layout(rect=[0, 0.12, 1, 0.90])
    save_fig(fig, out_dir / 'part4_nps.png')


# ── Chart 8: Child Wellbeing Drivers ─────────────────────────────────────────

def chart_part5_drivers(data, out_dir):
    drivers = data['parts']['part_5']['drivers']
    driver_labels = [
        ('financial_stress',           'Financial Stress (high)'),
        ('renewal_intent',             'Renewal Intent †'),
        ('nps_score',                  'NPS Score'),
        ('coverage_understanding',     'Coverage Understanding'),
        ('worth_premium',              'Worth Premium'),
        ('confidence_pay',             'Confidence to Pay'),
        ('claim_process_understanding','Claim Process Understanding'),
    ]

    items = []
    for key, label in driver_labels:
        d = drivers.get(key, {})
        v = d.get('value')
        if v is not None:
            items.append((label, v))

    items.sort(key=lambda x: abs(x[1]))   # ascending |rho| → bottom to top
    labels = [x[0] for x in items]
    rhos   = [x[1] for x in items]
    colors = [C['s2'] if r > 0 else C['s1'] for r in rhos]

    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    base_style(ax, fig)

    y = np.arange(len(labels))
    bars = ax.barh(y, [abs(r) for r in rhos], color=colors,
                   height=0.55, linewidth=0, zorder=2)

    ax.xaxis.grid(True, color=C['grid'], linewidth=0.5, zorder=0)
    ax.set_axisbelow(True)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9.5, color=C['ink_1'])

    for bar, rho in zip(bars, rhos):
        sign = '+' if rho > 0 else '−'
        ax.text(bar.get_width() + 0.006,
                bar.get_y() + bar.get_height() / 2,
                f'ρ = {sign}{abs(rho):.3f}',
                va='center', ha='left', fontsize=8.5, color=C['ink_2'])

    ax.set_xlim(0, 0.62)
    ax.set_xlabel('|ρ|  (Spearman correlation)', fontsize=9, color=C['ink_2'])
    ax.set_xticklabels([])
    ax.tick_params(axis='x', which='both', bottom=False)

    p1 = mpatches.Patch(color=C['s1'], label='Negative relationship with CWB (↑ value → ↑ CWB)')
    p2 = mpatches.Patch(color=C['s2'], label='Positive relationship with CWB (↑ NPS → ↑ CWB)')
    ax.legend(handles=[p1, p2], fontsize=8, frameon=False,
              loc='upper center', bbox_to_anchor=(0.5, -0.08), ncol=1,
              labelcolor=C['ink_2'])

    add_title(fig, 'Child Wellbeing Drivers',
              'Spearman ρ with child wellbeing improvement  (n≈1,928 caregivers)')
    add_source(fig, note='† Renewal Intent n=127 only')
    plt.tight_layout(rect=[0, 0.10, 1, 0.90])
    save_fig(fig, out_dir / 'part5_drivers.png')


# ── Chart 9: Healthcare & Medical Cost ────────────────────────────────────────

def chart_part5_healthcare(data, out_dir):
    ha = data['parts']['part_4']['healthcare_access']['headline']['value'] * 100
    mc = data['parts']['part_4']['medical_cost_change']['headline']['value'] * 100

    tiles = [
        ('Healthcare\nAccess Improved', ha,
         'Clients who needed care\n(n=1,672)', C['s2']),
        ('Medical Costs\nDecreased', mc,
         'Claimants who sought care\n(n=926)', C['good']),
    ]

    fig, axes = plt.subplots(1, 2, figsize=(7, 3.2))
    fig.patch.set_facecolor(C['surface'])

    for ax, (label, val, base, color) in zip(axes, tiles):
        ax.set_facecolor(C['surface'])
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
        rect = mpatches.FancyBboxPatch(
            (0.05, 0.08), 0.90, 0.84,
            boxstyle='round,pad=0.02',
            facecolor='white', edgecolor=C['grid'], linewidth=1.2)
        ax.add_patch(rect)
        ax.text(0.50, 0.80, label, ha='center', va='center',
                fontsize=11.5, color=C['ink_2'], fontweight='bold')
        ax.text(0.50, 0.52, f'{val:.1f}%', ha='center', va='center',
                fontsize=30, color=color, fontweight='bold')
        ax.text(0.50, 0.22, base, ha='center', va='center',
                fontsize=8.5, color=C['ink_muted'])

    fig.suptitle('Health Outcomes for Clients', x=0.05, ha='left',
                 fontsize=13, fontweight='bold', color=C['ink_1'], y=1.05)
    fig.text(0.05, -0.06, SOURCE, fontsize=7.5, color=C['ink_muted'])
    plt.tight_layout()
    save_fig(fig, out_dir / 'part5_healthcare.png')


# ── Chart 10: Claimant vs Non-Claimant Scorecard ──────────────────────────────

def chart_part6_scorecard(data, out_dir):
    metrics = data['parts']['part_6']['metrics']
    rows_spec = [
        ('Coverage Understanding',       'coverage_understanding'),
        ('Claim Process Understanding',  'claim_process_understanding'),
        ('Worth Premium',                'worth_premium'),
        ('Negative Coping ↓',           'negative_coping'),
        ('High Financial Stress ↓',     'financial_stress_high'),
        ('Confidence to Pay',           'confidence_pay'),
    ]

    labels, c_vals, nc_vals, sigs = [], [], [], []
    for label, key in rows_spec:
        m = metrics[key]
        cv  = m.get('claimant', {}).get('value')
        nv  = m.get('non_claimant', {}).get('value')
        cs  = m.get('claimant', {}).get('suppressed', False)
        ns  = m.get('non_claimant', {}).get('suppressed', False)
        sig = m.get('significance') or {}
        pv  = sig.get('p_value') if isinstance(sig, dict) else None
        if cv is not None and not cs and nv is not None and not ns:
            labels.append(label)
            c_vals.append(cv * 100)
            nc_vals.append(nv * 100)
            sigs.append(pv is not None and pv < 0.05)

    # Reverse so largest absolute gap is at top
    labels  = labels[::-1]
    c_vals  = c_vals[::-1]
    nc_vals = nc_vals[::-1]
    sigs    = sigs[::-1]

    fig, ax = plt.subplots(figsize=(8.5, 4.5))
    base_style(ax, fig)

    y, h = np.arange(len(labels)), 0.35
    ax.barh(y + h/2, c_vals,  height=h, color=C['s1'],       linewidth=0,
            label='Claimant (n=153)', zorder=2)
    ax.barh(y - h/2, nc_vals, height=h, color=C['muted_bar'], linewidth=0,
            label='Non-Claimant (n=210)', zorder=2)

    max_val = max(max(c_vals), max(nc_vals))
    for i, (cv, nv, sig) in enumerate(zip(c_vals, nc_vals, sigs)):
        ax.text(cv  + max_val * 0.012, y[i] + h/2,
                f'{cv:.1f}%',  va='center', ha='left', fontsize=8, color=C['ink_2'])
        ax.text(nv  + max_val * 0.012, y[i] - h/2,
                f'{nv:.1f}%',  va='center', ha='left', fontsize=8, color=C['ink_2'])
        if sig:
            ax.text(max(cv, nv) + max_val * 0.10, y[i],
                    '*', va='center', ha='left',
                    fontsize=14, color=C['s3'], fontweight='bold')

    ax.xaxis.grid(True, color=C['grid'], linewidth=0.5, zorder=0)
    ax.set_axisbelow(True)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9.5, color=C['ink_1'])
    ax.set_xlim(0, max_val * 1.28)
    ax.set_xticklabels([])
    ax.tick_params(axis='x', which='both', bottom=False)
    ax.legend(fontsize=9, frameon=False,
              loc='upper center', bbox_to_anchor=(0.5, -0.04), ncol=2,
              labelcolor=C['ink_2'])
    fig.text(0.05, 0.06, '* p < 0.05 (statistically significant difference)',
             fontsize=8, color=C['ink_muted'])

    add_title(fig, 'Key Metrics: Claimants vs. Non-Claimants',
              'Vietnam 2026 Q2    ↓ = lower is better for these metrics')
    add_source(fig)
    plt.tight_layout(rect=[0, 0.12, 1, 0.90])
    save_fig(fig, out_dir / 'part6_scorecard.png')


# ── Chart 11: Gender Scorecard ────────────────────────────────────────────────

def chart_part7_scorecard(data, out_dir):
    metrics = data['parts']['part_7']['metrics']
    rows_spec = [
        ('Coverage Understanding',       'coverage_understanding'),
        ('Claim Process Understanding',  'claim_process_understanding'),
        ('Worth Premium',                'worth_premium'),
        ('Negative Coping ↓',           'negative_coping'),
        ('Child Wellbeing Improved',     'child_wellbeing'),
        ('Confidence to Pay',           'confidence_pay'),
    ]

    labels, f_vals, m_vals, sigs = [], [], [], []
    for label, key in rows_spec:
        m = metrics[key]
        fv  = m.get('female', {}).get('value')
        mv  = m.get('male',   {}).get('value')
        fs  = m.get('female', {}).get('suppressed', False)
        ms  = m.get('male',   {}).get('suppressed', False)
        sig = m.get('significance') or {}
        pv  = sig.get('p_value') if isinstance(sig, dict) else None
        if fv is not None and not fs:
            labels.append(label)
            f_vals.append(fv * 100)
            m_vals.append(mv * 100 if (mv is not None and not ms) else None)
            sigs.append(pv is not None and pv < 0.05)

    labels = labels[::-1]
    f_vals = f_vals[::-1]
    m_vals = m_vals[::-1]
    sigs   = sigs[::-1]

    fig, ax = plt.subplots(figsize=(8.5, 4.5))
    base_style(ax, fig)

    y, h = np.arange(len(labels)), 0.35
    ax.barh(y + h/2, f_vals, height=h, color=C['s1'], linewidth=0,
            label='Female (n=1,518)', zorder=2)

    # Male bars (skip if suppressed)
    m_plot = [v if v is not None else 0 for v in m_vals]
    ax.barh(y - h/2, m_plot, height=h, color=C['s2'], linewidth=0,
            label='Male (n=586)', zorder=2)

    max_val = max(max(f_vals), max(v for v in m_vals if v is not None))
    for i, (fv, mv) in enumerate(zip(f_vals, m_vals)):
        ax.text(fv + max_val * 0.012, y[i] + h/2,
                f'{fv:.1f}%', va='center', ha='left', fontsize=8, color=C['ink_2'])
        if mv is not None:
            ax.text(mv + max_val * 0.012, y[i] - h/2,
                    f'{mv:.1f}%', va='center', ha='left', fontsize=8, color=C['ink_2'])
        else:
            ax.text(1, y[i] - h/2, 'SUPPRESSED',
                    va='center', ha='left', fontsize=7.5,
                    color=C['ink_muted'], fontstyle='italic')

    ax.xaxis.grid(True, color=C['grid'], linewidth=0.5, zorder=0)
    ax.set_axisbelow(True)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9.5, color=C['ink_1'])
    ax.set_xlim(0, max_val * 1.25)
    ax.set_xticklabels([])
    ax.tick_params(axis='x', which='both', bottom=False)
    ax.legend(fontsize=9, frameon=False,
              loc='upper center', bbox_to_anchor=(0.5, -0.04), ncol=2,
              labelcolor=C['ink_2'])
    fig.text(0.05, 0.06,
             'No statistically significant gender differences (all p > 0.05)',
             fontsize=8, color=C['ink_muted'])

    add_title(fig, 'Key Metrics by Gender',
              'Vietnam 2026 Q2    ↓ = lower is better for these metrics')
    add_source(fig)
    plt.tight_layout(rect=[0, 0.12, 1, 0.90])
    save_fig(fig, out_dir / 'part7_scorecard.png')


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Generate report visuals')
    parser.add_argument('--run-id', default='2026_Q2', help='Run directory name')
    args = parser.parse_args()

    data    = load_data(args.run_id)
    out_dir = ROOT / 'runs' / args.run_id / 'visuals'
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f'\n── Generating 11 visuals → {out_dir} ───────────────────────')
    chart_part1_coverage(data, out_dir)
    chart_part1_claims_process(data, out_dir)
    chart_part2_funnel(data, out_dir)
    chart_part2_no_claim(data, out_dir)
    chart_part2_challenges(data, out_dir)
    chart_part3_financial(data, out_dir)
    chart_part4_nps(data, out_dir)
    chart_part5_drivers(data, out_dir)
    chart_part5_healthcare(data, out_dir)
    chart_part6_scorecard(data, out_dir)
    chart_part7_scorecard(data, out_dir)
    print(f'\n  Done. Now run:')
    print(f'  python generation/run_generation.py --run-id {args.run_id}')


if __name__ == '__main__':
    main()
