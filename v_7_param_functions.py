# coding: utf-8
####################
# Import libraries #
####################
# Importing libraries within function is not allowed so it is done here
from __future__ import division     # Without this, rounding errors occur in python 2.7, but apparently not in 3.4
import pandas as pd  # CSV handling
import math
import datetime  # For time stamping optimisation procs

"""Library of functions for parsing parameter and exogenous variable data and passing to the scenario_manager script"""

def make_scenario_dict(file, s):
    """This function takes the CSV containing s scenarios and converts the s_th row to a dictionary for use in
    the rest of the script."""
    s_dict = {'scenario': file['scenario'][s],
              'P_inv_cont': file['P_inv_cont'][s],
              'R_ac_dc': file['R_ac_dc'][s],
              'EtoP': file['EtoP'][s],
              'SOC_0': file['SOC_0'][s],
              'tariff_key': file['tariff_key'][s],
              'tariff_prices': file['tariff_prices'][s],
              'load_profile': file['load_profile'][s],
              'wholesale_profile': file['wholesale_profile'][s],
              'AS_profiles': file['AS_profiles'][s],
              'ARD': file['ARD'][s],
              'ARU': file['ARU'][s],
              'WRD': file['WRD'][s],
              'WRU': file['WRU'][s],
              'CER': file['CER'][s],
              'time-step_h': file['time-step_h'][s],
              'win_opt': file['win_opt'][s],
              'win_actioned': file['win_actioned'][s],
              'BESS': file['BESS'][s],
              'SOC_min': file['SOC_min'][s],
              'SOC_max': file['SOC_max'][s],
              'DC_fudge': file['DC_fudge'][s],
              'project_year_cap': file["project_year_cap"][s],
              'day_prog': file['day_prog'][s],
              'P_cap': file['P_cap'][s],
              'verbose': file['verbose'][s],
              'T': file['T_K'][s],
              'EOL': file['EOL'][s],
              'export_cap': file['export_cap'][s],
              'days': 1, # Start a day tracker for calendar ageing calcs
              'o_m_cost': file['o_m_cost'][s],
              'may_maint': file['may_maint'][s], # Fix electrolyte maintenance to happen in May
              'cap_init': file['cap_init'][s]  # This param allows us to nudge the maintenance of the VRFB around.
              }
    return s_dict

def make_BESS_param_dict(s_dict, BESS_csv):
    df = pd.read_csv(BESS_csv)
    row = df['BESS'].tolist().index(s_dict['BESS'])  # Look up appropriate row for given BESS class
    # Read in params that are BESS class agnostic (note, for RFB I units Am-2, otherwise A.unit-1)
    BESS_dict = {'BESS_class': df['BESS_class'][row],
                 'Eff_LP': df['Eff_LP'][row]}
    BESS_dict['C_0'] = s_dict['P_inv_cont'] * s_dict['EtoP']
    BESS_dict.update({'C': BESS_dict['C_0']*s_dict['cap_init']}) # Mutable capacity entry. Starting point alterable.
    if BESS_dict['BESS_class'] == 'VRFB':
        BESS_dict.update({'EDR': float(df['EDR'][row]),
                          'CFR': float(df['CFR'][row])}) # If VRFB, read the electrolyte decay and capacity fade rates
    BESS_dict['Q'] = 1  # Track charge throughput in EFC, init. with 1 to avoid problems with algebra on 0
    return BESS_dict

def parse_k_u_periods(file):
    file = pd.read_csv(file)
    # Make a dictionary that will serve as lookup table
    k_u_dict = {(file['mm'][i],
                 file['wk_wknd'][i],
                 file['hh'][i]):
                [file['k'][i], file['u'][i]]
                for i in range(len(file['mm']))
                }
    return k_u_dict

def parse_exog_variable_data(load_CSV, k_u_dict, w_csv, AS_csv, time_step):
    """This function constructs two lists of exogenous variable data - one at 15 min (for load, and unit charges) and
    one at hourly resolution for ancillary services"""
    # 15 min res data
    c = 3  # converts 5 min res load to 15 min - adjust if desired
    load = pd.read_csv(load_CSV)['value'].tolist()
    date = pd.read_csv(load_CSV)['local_time']
    wholesale_energy = pd.read_csv(w_csv)['MW'] # This is the $/MWh price
    # Make exogenous variable list of lists, with format
    # [[[yyyy, mm, dd, hh, min, day_of_week], [day_of_week, load, k, u]] ... ]
    exog_variable_l_o_l_t = []

    for i in range(int(len(load)/c)):
        ts = date[i*c]
        min = int(ts[14:16])
        hh = int(ts[11:13])
        dd = int(ts[0:2])
        mm = int(ts[3:5])
        yyyy = int(ts[6:10])
        day_of_week = datetime.datetime(yyyy, mm, dd).strftime("%A")  # Returns day of week
        # Generate k and u using the k_u_dict
        if day_of_week in ['Saturday', 'Sunday']:
            k = k_u_dict[mm, 'wknd', hh][0]
            u = k_u_dict[mm, 'wknd', hh][1]
        else:
            k = k_u_dict[mm, 'wk', hh][0]
            u = k_u_dict[mm, 'wk', hh][1]
        # Generate w by pulling out entries from w CSV, converting i from 15min index to 1h
        w = wholesale_energy[int(i/4)] / 1000  # And convert price to $/kWh
        exog_variable_l_o_l_t += [[[yyyy, mm, dd, hh, min], [day_of_week, (1/time_step)*sum(load[i * c: (i * c) + c]),
                                                              k, u, w]]]
    # 1 hour res data
    spin_reserve = pd.read_csv(AS_csv)['SP_CLR_PRC']  # This is the $/MWh price
    reg_down = pd.read_csv(AS_csv)['RD_CLR_PRC']  # This is the $/MWh price
    reg_up = pd.read_csv(AS_csv)['RU_CLR_PRC']  # This is the $/MWh price
    exog_variable_l_o_l_h = []
    c = 12  # conversion factor 5 min to 1h - adjust if desired
    for i in range(int(len(load)/c)):
        ts = date[i*c]
        hh = int(ts[11:13])
        dd = int(ts[0:2])
        mm = int(ts[3:5])
        yyyy = int(ts[6:10])
        day_of_week = datetime.datetime(yyyy, mm, dd).strftime("%A")  # Returns day of week
        s = spin_reserve[i] / 1000  # Convert price to $/kWh
        r_d = reg_down[i] / 1000
        r_u =reg_up[i] / 1000
        exog_variable_l_o_l_h += [[[yyyy, mm, dd, hh], [s, r_d, r_u]]]
    return exog_variable_l_o_l_t, exog_variable_l_o_l_h


def grab_month_exog(exog_variables_t, exog_variables_h, mm, year, time_step):
    """This function grabs a month portion of exogenous data for use in the monthly optimsiation.
    It also grabs a day from the following month to provide a buffer in case the optimsiaiton window is > 24h."""
    m_of_load, m_of_k, m_of_u, m_of_w = [], [], [], []
    peak_loads_m = {}  # For tracking peak loads in each sub_period (to be used later in revenue calculation)
    peak_loads_buffer = {}  # Also need to catch k for buffer period falling in new month (avoid index error may > june)
    for i in exog_variables_t:
        load, k, u, w = i[1][1], i[1][2], i[1][3], i[1][4]
        if i[0][0] == year and i[0][1] == mm:  # Current month test
            m_of_load += [load]
            m_of_k += [k]
            m_of_u += [u]
            m_of_w += [w]
            if k in peak_loads_m.keys():
                if load > peak_loads_m[k]:  # Is load higher than existing peak in this demand charge sub-period?
                    peak_loads_m[k] = load  # If so overwrite record
            else:
                peak_loads_m.update({k: load})

        elif i[0][0] == year and i[0][1] == mm + 1 and i[0][2] == 1:  # First day from following month
            m_of_load += [load]
            m_of_k += [k]
            m_of_u += [u]
            m_of_w += [w]
            if k not in peak_loads_m.keys():
                if k in peak_loads_buffer.keys():
                    peak_loads_buffer[k] = load
                else:
                    peak_loads_buffer.update({k: load})
    peak_loads_buffer.update(peak_loads_m)
    # Special case for December where buffer day is taken from following year
    if mm == 12:
        for i in exog_variables_t:
            if i[0][0] == year + 1 and i[0][1] == 1 and i[0][2] == 1:  # First day from next year
                m_of_load += [load]
                m_of_k += [k]
                m_of_u += [u]
                m_of_w += [w]
    # Convert hourly AS clearing prices to timestep resolution by duplication
    m_of_s, m_of_r_d, m_of_r_u = [], [], []
    for i in exog_variables_h:
        s, r_d, r_u = i[1][0], i[1][1], i[1][2]
        if i[0][0] == year and i[0][1] == mm:
            m_of_s += [s for i in range(int(1/time_step))]
            m_of_r_d += [r_d for i in range(int(1/time_step))]
            m_of_r_u += [r_u for i in range(int(1/time_step))]
        elif i[0][0] ==year and i[0][1] == mm+1 and i[0][2] == 1:
            m_of_s += [s, s, s, s]
            m_of_r_d += [r_d for i in range(int(1/time_step))]
            m_of_r_u += [r_u for i in range(int(1/time_step))]
    # Special case for December where buffer day is taken from following year
    if mm == 12:
        for i in exog_variables_h:
            s, r = i[1][0], i[1][1]
            if i[0][0] == year + 1 and i[0][1] == 1 and i[0][2] == 1:  # First day from next year
                m_of_s += [s for i in range(int(1 / time_step))]
                m_of_r_d += [r_d for i in range(int(1 / time_step))]
                m_of_r_u += [r_u for i in range(int(1 / time_step))]
    return m_of_load, m_of_k, m_of_u, m_of_w, m_of_s, m_of_r_d, m_of_r_u, peak_loads_m, peak_loads_buffer

def day_results(time_step, load, c_log, d_log, U, W):
    """This function returns the relevant data from the optimal schedule for a given day, to be used in upper level
    calculation of monthly revenue."""
    # Make list of ACTUAL net load, i.e. incoming load_profile net of 'optimal' schedule based on historic load
    T = range(int(len(load)))
    net_load_profile = []
    for t in T:
        net_load_profile += [load[t] + c_log[t] - d_log[t]]
    # Calculate daily avoided cost in U and W
    ac_u_d = sum([(d_log[t] - c_log[t]) * U[t] * time_step for t in T])
    ac_w_d = sum([(d_log[t] - c_log[t]) * W[t] * time_step for t in T])
    # Calculate daily revenue from AS provision
    return ac_u_d, ac_w_d, net_load_profile

def parse_verbose(verbose_results, load, c_log, d_log, SOC_profile, demand_profile,
                                         yyyy, mm, dd, k, u, w):
    """This function builds an optional verbose output of BESS operation at the resoltuion of the model timestep."""
    T = range(int(len(load)))
    verbose_results['yyyy'] += [yyyy for t in T]
    verbose_results['mm'] += [mm for t in T]
    verbose_results['dd'] += [dd + 1 for t in T]  # =1 to match labels in python output
    verbose_results['period'] += [t+1 for t in T]
    verbose_results['k'] += [k[t] for t in T]
    verbose_results['u'] += [u[t] for t in T]
    verbose_results['w'] += [w[t] for t in T]
    verbose_results['load'] += [load[t] for t in T]
    verbose_results['P'] += [c_log[t] - d_log[t] for t in T]
    verbose_results['net_load'] += [demand_profile[t] for t in T]
    verbose_results['SOC'] += [SOC_profile[t] for t in T]
    return verbose_results
