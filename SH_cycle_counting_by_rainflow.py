import csv
import numpy as np
import math
import scipy
import matplotlib.pyplot as plt


# Finds peaks and valleys in a SoC time series and returns a reduced time series that only
# contains these peaks and valleys (all other data points are deleted). The function also finds
# the periods when the battery is idling at the same SoC (defined as the time when the SoC
# changes by less than 5e-6); this info is stored in the idle array.
def find_pkvl_and_idle(SoC):
	SoC = np.array(SoC)
	dlt = []
	idle = []

    # This loop goes through each element of the SoC array and if the element is different to
	# the adjacent elements, then it is left alone. If the element is the same as the adjacent
	# elements (within 5e-6), then its index is recorded in the delete list and the idle array.
	# There is a flaw in this method: the SoC could increase from 0.4 to 0.8 in increments of
	# 4e-6, for example, but the method would recognise the battery as idling the entire time!
	for i in range(0,SoC.size):
		if i==0:
			if np.isclose(SoC[i], SoC[i+1], rtol=0, atol=5e-6):
				dlt.append(i)
				idle.append(SoC[i])
		if i==SoC.size-1:
			if np.isclose(SoC[i], SoC[i-1], rtol=0, atol=5e-6):
				dlt.append(i)
				idle.append(SoC[i])		
		elif (np.isclose(SoC[i-1], SoC[i], rtol=0, atol=5e-6) and np.isclose(SoC[i],
		SoC[i+1], rtol=0, atol=5e-6)):
			dlt.append(i)
			idle.append(SoC[i])
		else:
			continue

	idle = np.array(idle)
	idle = 1e5*np.round(idle, decimals=5)
	idle = idle.astype(int)

	# A new array is created 'SoC_noflat' that is the same as 'SoC' but with the flat sections
	# removed. Only one data point from a flat section is kept (the one that's furthest to the
	# right). dlt must be a list not a numpy array.
	SoC_noflat = np.delete(SoC, dlt)
	
	dlt = []

	# This loop goes through each element of the SoC_noflat array and if the element is a peak
	# or a valley, then it is left alone. If the element is not a peak or a valley, then its
	# index is recorded in the delete list.
	for i in range(1,SoC_noflat.size-1):
		if SoC_noflat[i] == SoC_noflat[i-1]:
			if SoC_noflat[i] > SoC_noflat[i-2] and SoC_noflat[i] > SoC_noflat[i+1]:
				continue
			if SoC_noflat[i] < SoC_noflat[i-2] and SoC_noflat[i] < SoC_noflat[i+1]:
				continue
			if SoC_noflat[i] > SoC_noflat[i-2] and SoC_noflat[i] < SoC_noflat[i+1]:
				dlt.append(i)
			if SoC_noflat[i] < SoC_noflat[i-2] and SoC_noflat[i] > SoC_noflat[i+1]:
				dlt.append(i)
		else:
			if SoC_noflat[i] > SoC_noflat[i-1] and SoC_noflat[i] > SoC_noflat[i+1]:
				continue
			elif SoC_noflat[i] < SoC_noflat[i-1] and SoC_noflat[i] < SoC_noflat[i+1]:
				continue
			else:
				dlt.append(i)

	#A new array is created 'SoC_pkvl' that only contains alternate peaks and valleys.
	SoC_pkvl = np.delete(SoC_noflat, dlt)

	#return(SoC_pkvl, SoC_noflat, idle)
	return(SoC_pkvl)


# Finds half and whole cycles within the SoC_pkvl time series. Two arrays are created (one for
# half-cycles and one for whole-cycles) which have cycle depths in the 1st row and average SoC
# in the 2nd row.
def rfc_find_cycles(SoC_pkvl):

	v = np.array([]) #Rainflow counting vector (1D)
	hc = np.array([[],[]]) #Stores the cycle depth and average SoC of half-cycles (2D)
	wc = np.array([[],[]]) #Stores the cycle depth and average SoC of whole-cycles (2D)
	v = np.append(v, SoC_pkvl[0])
	v = np.append(v, SoC_pkvl[1])

	#This is the algorithm as described in the ASTM paper
	for i in range(2,SoC_pkvl.size):

		v = np.append(v, SoC_pkvl[i])
		while v.size >= 3:
			x = abs(v[-2] - v[-1])
			y = abs(v[-3] - v[-2])
			if x < y:
				break
			else:
				if v.size == 3:
					hc = np.append(hc, [[y],[(v[-3]+v[-2])/2]], axis=1)
					v = np.delete(v, -3)
				else:
					wc = np.append(wc, [[y],[(v[-3]+v[-2])/2]], axis=1)
					v = np.delete(v, -2)
					v = np.delete(v, -2)
	for i in range(0,v.size-1):
		y = abs(v[i]-v[i+1])
		hc = np.append(hc, [[y],[(v[i]+v[i+1])/2]], axis=1)

	hc = 1*np.round(hc, decimals=5)
	wc = 1*np.round(wc, decimals=5)

	#This is a very important step! If the elements in the arrays stay as floats then '=='
	#comparisons later don't always work.
	#hc = hc.astype(int)
	#wc = wc.astype(int)

	#print(np.size(hc,axis=1))
	#print(np.size(wc,axis=1))

	hc = hc[:, hc[0,:]!=0]
	wc = wc[:, wc[0,:]!=0]

	#print(np.size(hc,axis=1))
	#print(np.size(wc,axis=1))
	


	return hc, wc
