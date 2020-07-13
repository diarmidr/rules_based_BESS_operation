# coding: utf-8
####################
# Import libraries #
####################
# Importing libraries within function is not allowed so it is done here
from __future__ import division     # Without this, rounding errors occur in python 2.7, but apparently not in 3.4
import math
# For data_mgmt_by_list
import pandas as pd  # CSV handling
# Sam Homan's rainflow algorithm for identifying cycles with a schedule, and their associated mean SOC
from SH_cycle_counting_by_rainflow import *

def VRFB_elec_decay(mm, dd, s_dict, BESS_dict, SOC_profile):
    """As VRFB cap. fade is only dependent on cycle throughput in our formulation (as per Rodby et al.) a simple
    SOC tracker may be used, rather than the SH rainflow counter required for Li-ion."""
    # Schedule input for function needs to include SOC_0 point.
    schedule = [s_dict['SOC_0']] + [SOC_profile[i] for i in range(s_dict['win_actioned'] * 4)]
    q = 0  # E throughput in equivalent full cycles
    for i in range(len(schedule)-1):
        if schedule[i+1] > schedule[i]:
            q += (schedule[i+1] - schedule[i])/2
        else:
            q += (schedule[i] - schedule[i+1])/2
    BESS_dict['Q'] += q  # Convert from SOC travel to cycles
    print('Cycles performed:', "%.2f" % (q))
    if s_dict['may_maint'] == 1:  # In this branch, maintenance always occurs on last day in May
        # If capacity drops below permitted limit, perform maintenance operation and log cost
        if mm == 5:
            if dd == 30:  # Last day of May (first day is 0)
                BESS_dict['C'] = BESS_dict['C_0']
                o_and_m_d = s_dict['o_m_cost'] * BESS_dict['C_0']
            else:
                BESS_dict['C'] -= (q * BESS_dict['EDR'] * BESS_dict['C_0'])  # Cap loss due to electrolyte decay
                o_and_m_d = 0
        else:
            BESS_dict['C'] -= (q * BESS_dict['EDR'] * BESS_dict['C_0'])  # Cap loss due to electrolyte decay
            o_and_m_d = 0
    else:  # If not fixing the maintenance in May, just let it decay to show what happens
        BESS_dict['C'] -= (q * BESS_dict['EDR'] * BESS_dict['C_0'])  # Cap loss due to electrolyte decay
        o_and_m_d = 0
    print('Capacity fraction', "%.2f" % (BESS_dict['C']/BESS_dict['C_0']))
    return o_and_m_d, q

def VRFB_rebalance_cost(q, BESS_dict, U, W):
    f = q * BESS_dict['CFR']  # % Capacity fade due to cycles performed
    delta_ox = 4 - (2 * f * 3.5 + (1 - f) * 4)/(1 + f)
    U_r = sum(U[0:31])/32  # Average price of retail energy in rebalance period
    W_r = sum(W[0:31])/32  # Average price of wholesale energy in rebalance period
    rebalance_cost_d = BESS_dict['C'] * delta_ox * (U_r + W_r) / math.sqrt(BESS_dict['Eff_LP'])
    return rebalance_cost_d