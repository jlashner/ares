"""

test_21cm.py

Author: Jordan Mirocha
Affiliation: University of Colorado at Boulder
Created on: Mon Oct 1 15:23:53 2012

Description: Make sure the global 21-cm signal calculator works.

"""

import ares
import numpy as np
import matplotlib.pyplot as pl
from ares.physics.Constants import rhodot_cgs

pars = \
{
 'Tmin{0}': 1e4,
 'source_type{0}': 'star',
 'fstar{0}': 1e-1,
 'Nion{0}': 4e3,
 'Nlw{0}': 9600.,
 'Tmin{1}': 300.,
 'source_type{1}': 'star',
 'is_lya_src{1}': True,
 'is_ion_src_igm{1}': False,
 'is_ion_src_cgm{1}': False, 
 'is_heat_src_igm{1}': False, 
 'fstar{1}': 1e-4,
 'Nion{1}': 3e4,
 'Nlw{1}': 4800.,
}

# Dual-population model
sim = ares.simulations.Global21cm(**pars)

sim.run()

anl = ares.analysis.Global21cm(sim)
ax = anl.GlobalSignature(color='k', label=r'dual-pop')

# Standard single population model - overplot
sim2 = ares.simulations.Global21cm()
sim2.run()

anl2 = ares.analysis.Global21cm(sim2)
ax = anl2.GlobalSignature(ax=ax, color='b', label='single-pop')
