# coding: utf-8
"""This script is the top level one for running various scenarios in the behind
the meter case study described by Fisher et al. (2019). The script relies on two
CSV param files: one contains the BESS performance params, the other the
scenario params, e.g. the BESS sizing. The bulk of this script is devoted to
parsing the exogenous variable data set within the monthly framework required
for the demand charge billing."""

### Import required tools ###
from __future__ import division     # Without this, rounding errors occur in python 2.7, but apparently not in 3.4
import pandas as pd                 # CSV handling
import datetime                     # For time stamping optimisation process
from pyomo.environ import *         # For optimisation posement
# I've separated generic python functions and optimisation functions into two files to avoid huge lists of functions
from v_7_param_functions  import *
from v_7_algorithms import *
from v_7_deg_functions import *

######################
# Scenario iteration #
######################
run_time_by_case = []  # Receptacle for run time results
results_by_case = pd.DataFrame()  # Receptacle for results by case

scenarios = pd.read_csv('v_7_scenarios.csv')  # Import CSV file containing scenario rows
for s in range(len(scenarios)):
    start_time = datetime.datetime.now()  # Timestamp scenario analysis start
    # Import scenario parameters in dictionary format #
    s_dict = make_scenario_dict(scenarios, s)
    # Import exogenous variables #
    yyyy = 2012  # Script doesn't currently iterate over multiple years of data, but this is a placeholder for such
    k_u_dict = parse_k_u_periods(s_dict['tariff_key'])  # Get DNO charge periods w.r.t time in dictionary form.
    exog_variables_t, exog_variables_h = \
        parse_exog_variable_data(s_dict['load_profile'], k_u_dict, s_dict['wholesale_profile'],
                                 s_dict['AS_profiles'], s_dict['time-step_h'])
    tariff = pd.read_csv(s_dict['tariff_prices'])  # Get actual prices for DNO tariff
    u_periods, u_prices, k_periods, k_prices = \
        tariff['u_period'], tariff['u_price'], tariff['k_period'], tariff['k_price']
    k_charges = {}
    for i in range(len(k_periods)):
        if k_periods[i] == k_periods[i]:  # This test skips any Nan entries
            k_charges[i+1] = k_prices[i]
    u_charges = {u_periods[i]: u_prices[i] for i in range(len(u_periods))}  # populate u charge dictionary from csv
    print("Exogenous variable dataset successfully imported")

    # Define absolute BESS parameters based on scenario and specific BESS #
    BESS_dict = make_BESS_param_dict(s_dict, 'v_7_BESS_params.csv')
    # Output receptacles
    results_s_m = {"year":[], "mm":[], "AC_K":[], "AC_U":[], "AC_W":[], "Cap_frac":[], "Q":[],"o_m":[],
                   "rebalance_cost":[]}
    results_s_y = [["Year", "AC_K", "AC_U", "AC_W", "rebalance_cost"]]
    # Optional output at max res for analysis
    if s_dict['verbose'] == 1:  # Optional results at optimisation time-step resolution (graphs and troubleshooting)
        verbose_results = {"yyyy": [], "mm": [], "dd": [], "period": [], "k": [], "u": [], "w": [], "load": [],
                           "P": [], "net_load": [], "SOC": []}
    ####################################
    # Calendar + state based iteration #
    ####################################
    project_year = 0  # Project year counter
    project_year_cap = s_dict['project_year_cap']
    while project_year < project_year_cap:  # Prevents script running forever when degradation isn't limiting
        # Month loop (time unit for demand charge billing) #
        months = [m+1 for m in range(12)]
        #months = [7]
        monthly_results = []  # Receptacle for results at monthly resolution
        for mm in months:
            # Gather exog variable data for the month
            m_of_load, m_of_k, m_of_u, m_of_w, m_of_s, m_of_r_d, m_of_r_u, peak_loads_m, peak_loads_buffer = \
                    grab_month_exog(exog_variables_t, exog_variables_h, mm, yyyy, s_dict['time-step_h'])
            # Make dict to store net demand peaks in month so far (passed to solver to prevent redundant shaving)
            peak_demands_record = {1: 227, 2: 230, 3: 224} # Hard code an informed guess

            # Initial peak demands record heuristic.
            """This sets an initial peak demand for each sub-period, so that the
            BESS doesn't just start discharging right away. It is based on the average demand in the sub-period for 
            the coming month, but ignores the first 6 hours of the day where demand is always low.  This is not strictly
            future-blind, but I expect this could be done adequately with historic data."""
            print(peak_loads_m)
            peak_demands_record = {}
            for k in peak_loads_m:
                load_in_k = []
                for d in range(int(len(m_of_load)/96)-1):  # Per day loop
                    for t in range((d+1)*96 - 72, (d+1)*96):     # Per sub-period excluding first 6 hours
                        if m_of_k[t] == k:
                            load_in_k += [m_of_load[t]]
                if len(load_in_k) != 0:  # Avoids div by 0 error at weekends (when there is no k_2, k_3)
                    peak_demands_record.update({k: sum(load_in_k)/len(load_in_k)})
            # Initiate monthly counters for revenue streams
            AC_U_m, AC_W_m, AC_S_m, Q_m, o_and_m_m, rebalance_cost_m = 0, 0, 0, 0, 0, 0
            """This loop repeatedly sends a chunk of data to the optimisation function. There are three parameters
            that control this process: win_opt - the length of the sliding window in hours, win_actioned, the
            portion of the optimised schedule that is implemented and day_prog, the number of days the window moves
            on after each optimisation (usually 1)."""
            days_in_month = range(int(len(m_of_load) * s_dict['time-step_h'] / 24) - 1) # Minus 1 to cancel buffer day
            #days_in_month = [1,2]
            for dd in days_in_month:
                print('scenario', s_dict['scenario'], 'year', project_year, 'month', mm, 'day', dd + 1)
                window = range(int(dd * s_dict['day_prog'] * 96), int(dd * s_dict['day_prog'] * 96 + s_dict['win_opt']*4))
                # Get price data across optimisation window
                load, K, U, W, S, R_d, R_u = [], [], [], [], [], [], []
                for t in window:
                    load += [m_of_load[t]]  # Actual 36h of load that will occur
                    K += [m_of_k[t]]               # Keep as just k indices for now, as required in PYOMO part
                    U += [u_charges[m_of_u[t]]]
                    W += [m_of_w[t]]
                # Here we call the optimisation function #
                c_log, d_log, SOC_log, peak_demands_record = \
                    opt_peak_shave_rules_ASAP(s_dict, BESS_dict, load, K, peak_demands_record)
                # Record relevant data for the implemented schedule and update peak demand record for the month
                AC_U_d, AC_W_d, net_load_profile = \
                    day_results(s_dict['time-step_h'], load, c_log, d_log, U, W)

                AC_U_m += AC_U_d
                AC_W_m += AC_W_d

                #print('days in operation:', "%.0f" % s_dict['days'])
                s_dict['days'] += 1

                # Call electrolyte decay tracker function
                if BESS_dict['BESS_class'] == 'VRFB':
                    o_and_m_d, q = VRFB_elec_decay(mm, dd, s_dict, BESS_dict, SOC_log)
                    Q_m += q
                    o_and_m_m += o_and_m_d
                # Call capacity rebalance cost tracker function
                if BESS_dict['BESS_class'] == 'VRFB':
                    rebalance_cost = VRFB_rebalance_cost(q, BESS_dict, U, W)
                    rebalance_cost_m -= rebalance_cost
                # This code updates the SOC_0 value to be used in the following window
                s_dict['SOC_0'] = SOC_log[-1]
                #print("SOC at end of window: ", "%.2f" % s_dict['SOC_0'], "\n")

                # This optional code writes verbose results to the l_o_l
                if s_dict['verbose'] == 1:
                    verbose_results = parse_verbose(verbose_results, load, c_log, d_log, SOC_log, net_load_profile, yyyy, mm, dd, K,
                                                    U, W)

            # Wrap up results at monthly resolution
            AC_K_m = sum([k_charges[k] * (peak_loads_m[k] - peak_demands_record[k]) for k in peak_loads_m])

            # Add monthly res results to dict for output later
            results_s_m['year'] += [project_year]
            results_s_m['mm'] += [mm]
            results_s_m['AC_K'] += [AC_K_m]
            results_s_m['AC_U'] += [AC_U_m]
            results_s_m['AC_W'] += [AC_W_m]
            results_s_m['Cap_frac'] += [BESS_dict['C'] / BESS_dict['C_0']]
            results_s_m["Q"] += [Q_m]
            results_s_m['o_m'] += [o_and_m_m]
            results_s_m['rebalance_cost'] += [rebalance_cost_m]


        # Wrap up results at year end by summing monthly values
        results_s_y += [[project_year, sum(results_s_m['AC_K']), sum(results_s_m['AC_U']), sum(results_s_m['AC_W']),
                        sum(results_s_m['rebalance_cost'])]]

        # Progress year
        project_year += 1
        # Output scenario results (write at end of each year in case of interuption)
        results_s_m = pd.DataFrame(results_s_m)
        results_s_m.to_csv("scenario_" + str(s_dict['scenario']) + "_monthly_results.csv")
        results_s_y = pd.DataFrame(results_s_y)
        results_s_y.to_csv("scenario_" + str(s_dict['scenario']) + "_annual_results.csv")
    run_time = (datetime.datetime.now() - start_time).seconds
    run_time_by_case += [run_time]
    if s_dict['verbose'] == 1:
        verbose_output = pd.DataFrame(verbose_results)
        verbose_output.to_csv("scenario_" + str(s_dict['scenario']) + "_verbose_results.csv")

    print("run time by case: ", run_time_by_case)
