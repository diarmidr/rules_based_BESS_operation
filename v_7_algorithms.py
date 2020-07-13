# coding: utf-8
####################
# Import libraries #
####################
# Importing libraries within function is not allowed so it is done here
from __future__ import division     # Without this, rounding errors occur in python 2.7, but apparently not in 3.4

# For data_mgmt_by_list
import pandas as pd  # CSV handling
import math

# for price_dict
import datetime  # For time stamping optimisation process

# For nlp_scheduler
from pyomo.environ import *
from pyomo.common.timing import report_timing
from pyomo.gdp import *
from pyomo.opt import SolverFactory


def opt_peak_shave_rules_ASAP(s_dict, BESS_dict, load, K, peak_demands_m):
    """Rules based peak shaving algorithm."""

    # Index sets #
    # Primary index
    T = range(len(load))
    # Time-step (h)
    time_step = s_dict['time-step_h']

    ################
    """Parameters"""
    ################
    # Generic scalar BESS params
    p_max = s_dict['P_inv_cont'] * s_dict['P_cap']  # kW
    C = BESS_dict['C']
    soc_min = s_dict['SOC_min']
    soc_max = s_dict['SOC_max']
    # BESS specific params
    eff =BESS_dict['Eff_LP'] # Leave as python float to avoid slow sqrt performance

    # Here comes the peak shaving algorithm
    soc_0 = s_dict['SOC_0']  # Initialise SOC at start of period
    c_log, d_log, soc_log =[], [], []
    for t in T:
        # Charge battery?
        if load[t] < peak_demands_m[K[t]]:
            d_log += [0]
            c = min(p_max, peak_demands_m[K[t]] - load[t])  # Power constrained charging
            if soc_0 + (c * time_step * math.sqrt(eff))/C <= soc_max:
                soc = soc_0 + (c * time_step * math.sqrt(eff))/C
            else:
                c = (soc_max - soc_0)*C/(time_step*math.sqrt(eff)) # SOC constrained charging, derate power
                soc = soc_max  # Update SOC counter
            c_log += [c]
            soc_log += [soc]
            soc_0 = soc  # Update SOC counter
        else: # Discharge battery
            c_log += [0]
            d = min(p_max, load[t] - peak_demands_m[K[t]])  # Power constrained discharging
            if soc_0 - (d * time_step)/(math.sqrt(eff) * C) >= soc_min:
                soc = soc_0 - (d * time_step)/(math.sqrt(eff) * C)
            else:
                d = (soc_0 - soc_min)* C * math.sqrt(eff)/time_step # SOC constrained discharging, derate power
                soc = soc_min
            d_log += [d]
            soc_log += [soc]
            soc_0 = soc  # Update SOC counter
            # If BESS is unable to keep net load below the peak so far for the month, record must be updated.
            if load[t] - d > peak_demands_m[K[t]]:
                peak_demands_m[K[t]] = load[t] - d
    return c_log, d_log, soc_log, peak_demands_m


