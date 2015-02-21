"""

ModelFit.py

Author: Jordan Mirocha
Affiliation: University of Colorado at Boulder
Created on: Mon Apr 28 11:19:03 MDT 2014

Description: For analysis of MCMC fitting.

"""

import re, os
import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as pl
from ..util import ProgressBar
from ..physics import Cosmology
from .MultiPlot import MultiPanel
from ..inference import ModelGrid
from matplotlib.patches import Rectangle
from ..physics.Constants import nu_0_mhz
from .Global21cm import Global21cm as aG21
from ..util import labels as default_labels
from ..util.ParameterFile import count_populations
from .DerivedQuantities import DerivedQuantities as DQ
from ..simulations.Global21cm import Global21cm as sG21
from ..util.Stats import Gauss1D, GaussND, error_1D, rebin
from ..util.SetDefaultParameterValues import SetAllDefaults, TanhParameters
from ..util.ReadData import read_pickled_dict, read_pickle_file, \
    read_pickled_chain, read_pickled_logL

try:
   import cPickle as pickle
except:
   import pickle    
    
try:
    from mpi4py import MPI
    rank = MPI.COMM_WORLD.rank
    size = MPI.COMM_WORLD.size
except ImportError:
    rank = 0
    size = 1

tanh_pars = TanhParameters()

def_kwargs = {}

def parse_blobs(name):
    nsplit = name.split('_')
    
    if len(nsplit) == 2:
        pre, post = nsplit
    elif len(nsplit) == 3:
        pre, mid, post = nsplit
    
        pre = pre + mid
    
    if pre in default_labels:
        pass
        
    return None 

def subscriptify_str(s):

    raise NotImplementedError('fix me')
    
    if re.search("_", par):
        m = re.search(r"\{([0-9])\}", par)

    # If it already has a subscript, add to it

def logify_str(s, sub=None):
    s_no_dollar = str(s.replace('$', ''))
    
    if sub is not None:
        new_s = subscriptify_str(s_no_dollar)
    else:
        new_s = s_no_dollar
        
    return r'$\mathrm{log}_{10}' + new_s + '$'
        
def err_str(label, mu, err, log):
    l = str(label.replace('$', ''))

    if log:
        s = '\mathrm{log}_{10}' + l
    else:
        s = l

    s += '=%.3g^{+%.2g}_{-%.2g}' % (mu, err[0], err[1])
    
    return r'$%s$' % s

def def_par_names(N):
    return [i for i in np.arange(N)]

def def_par_labels(i):
    return 'parameter # %i' % i
                
class ModelSubSet(object):
    def __init__(self):
        pass

class ModelSet(object):
    def __init__(self, data):
        """
        Parameters
        ----------
        data : instance, str
            prefix for a bunch of files ending in .chain.pkl, .pinfo.pkl, etc.,
            or a ModelSubSet instance.

        """

        # Read in data from file (assumed to be pickled)
        if type(data) == str:
            prefix = data

            # Read MCMC chain
            self.chain = read_pickled_chain('%s.chain.pkl' % prefix)
            if rank == 0:
                print "Loaded %s.chain.pkl." % prefix

            # Figure out if this is an MCMC run or a model grid
            try:
                self.logL = read_pickled_logL('%s.logL.pkl' % prefix)
                if rank == 0:
                    print "Loaded %s.logL.pkl." % prefix
                self._is_mcmc = True
            except IOError:
                self._is_mcmc = False
            except ValueError:
                self.logL = None

            self.Nd = int(self.chain.shape[-1])
            
            if self._is_mcmc and os.path.exists('%s.facc.pkl' % prefix):
                f = open('%s.facc.pkl' % prefix, 'rb')
                self.facc = []
                while True:
                    try:
                        self.facc.append(pickle.load(f))
                    except EOFError:
                        break
                f.close()
                self.facc = np.array(self.facc)
                        
            # Read parameter names and info
            if os.path.exists('%s.pinfo.pkl' % prefix):
                f = open('%s.pinfo.pkl' % prefix, 'rb')
                self.parameters, self.is_log = pickle.load(f)
                f.close()

                if rank == 0:
                    print "Loaded %s.pinfo.pkl." % prefix
            else:
                self.parameters = range(self.Nd)
                self.is_log = [False] * self.Nd
            
            if os.path.exists('%s.blobs.pkl' % prefix):
                try:
                    blobs = read_pickle_file('%s.blobs.pkl' % prefix)
                    
                    if rank == 0:
                        print "Loaded %s.blobs.pkl." % prefix
                        
                    self.mask = np.zeros_like(blobs)    
                    self.mask[np.isinf(blobs)] = 1
                    self.mask[np.isnan(blobs)] = 1
                    self.blobs = np.ma.masked_array(blobs, mask=self.mask)
                except:
                    if rank == 0:
                        print "WARNING: Error loading blobs."    
                    
                f = open('%s.binfo.pkl' % prefix, 'rb')
                self.blob_names, self.blob_redshifts = \
                    map(list, pickle.load(f))
                f.close()

                if rank == 0:
                    print "Loaded %s.binfo.pkl." % prefix

            else:
                self.blobs = self.blob_names = self.blob_redshifts = None

            i = 0
            self.fails = []
            while os.path.exists('%s.fail_%i.pkl' % (prefix, i)):
            
                data = read_pickled_dict('%s.fail_%i.pkl' % (prefix, i))
                self.fails.extend(data)
                
                print "Loaded %s.fail_%i.pkl." % (prefix, i)
                i += 1
                
            if os.path.exists('%s.setup.pkl' % prefix):
                f = open('%s.setup.pkl' % prefix, 'rb')
                self.base_kwargs = pickle.load(f)
                f.close()
                
                if rank == 0:
                    print "Loaded %s.setup.pkl." % prefix
            else:
                self.base_kwargs = None    
                
            if not self.is_mcmc:
                
                self.grid = ModelGrid(**self.base_kwargs)
                
                self.axes = {}
                for i in range(self.chain.shape[1]):
                    self.axes[self.parameters[i]] = np.unique(self.chain[:,i])
                
                self.grid.set_axes(**self.axes)

                # Only exists for parallel runs
                if os.path.exists('%s.load.pkl' % prefix):
                    self.load = read_pickle_file('%s.load.pkl' % prefix)
                
                    if rank == 0:
                        print "Loaded %s.load.pkl." % prefix
                
        elif isinstance(data, ModelSubSet):
            self.chain = data.chain
            self.is_log = data.is_log
            self.base_kwargs = data.base_kwargs
            self.fails = data.fails
            
            self.mask = np.zeros_like(data.blobs)    
            self.mask[np.isinf(data.blobs)] = 1
            self.mask[np.isnan(data.blobs)] = 1
            self.blobs = np.ma.masked_array(data.blobs, mask=self.mask)

            self.blob_names = data.blob_names
            self.blob_redshifts = data.blob_redshifts
            self.parameters = data.parameters
            self.is_mcmc = data.is_mcmc
            
            if self.is_mcmc:
                self.logL = data.logL
            else:
                try:
                    self.load = data.load
                except AttributeError:
                    pass
                try:            
                    self.axes = data.axes
                except AttributeError:
                    pass
                try:
                    self.grid = data.grid
                except AttributeError:
                    pass

            self.Nd = int(self.chain.shape[-1])       
                
        else:
            raise TypeError('Argument must be ModelSubSet instance or filename prefix')              
    
        try:
            self._fix_up()
        except AttributeError:
            pass
    #@property
    #def chain(self):
    #    if not hasattr(self, '_chain'):
    #        if os.path.exists('%s.chain.pkl' % self.prefix):
                
    @property
    def Npops(self):
        if not hasattr(self, '_Npops') and self.base_kwargs is not None:
            self._Npops = count_populations(**self.base_kwargs)
        elif self.base_kwargs is None:
            self._Npops = 1
    
        return self._Npops
    
    def _fix_up(self):
        
        if not hasattr(self, 'blobs'):
            return
        
        if not hasattr(self, 'chain'):
            return
        
        if self.blobs.shape[0] == self.chain.shape[0]:
            return
            
        # Force them to be the same shape. The shapes might mismatch if
        # one processor fails to write to disk (or just hasn't quite yet),
        # or for more pathological reasons I haven't thought of yet.
                        
        if self.blobs.shape[0] > self.chain.shape[0]:
            tmp = self.blobs[0:self.chain.shape[0]]
            self.blobs = tmp
        else:
            tmp = self.chain[0:self.blobs.shape[0]]
            self.chain = tmp
    
    def _load(self, fn):
        if os.path.exists(fn):
            return read_pickle_file(fn)
    
    @property
    def is_mcmc(self):
        if not hasattr(self, '_is_mcmc'):
            self._is_mcmc = False
        
        return self._is_mcmc
    
    @is_mcmc.setter
    def is_mcmc(self, value):
        self._is_mcmc = value
    
    @property    
    def blob_redshifts_float(self):
        if not hasattr(self, '_blob_redshifts_float'):
            self._blob_redshifts_float = []
            for i, redshift in enumerate(self.blob_redshifts):
                if type(redshift) is str:
                    z = None
                else:
                    z = redshift
                    
                self._blob_redshifts_float.append(z)
            
        return self._blob_redshifts_float
    
    def SelectModels(self):
        """
        Draw a rectangle on supplied matplotlib.axes.Axes instance, return
        information about those models.
        """
                
        if not hasattr(self, '_ax'):
            raise AttributeError('No axis found.')        
                
        self._op = self._ax.figure.canvas.mpl_connect('button_press_event', 
            self._on_press)
        self._or = self._ax.figure.canvas.mpl_connect('button_release_event', 
            self._on_release)
                            
    def _on_press(self, event):
        self.x0 = event.xdata
        self.y0 = event.ydata
        
    def _on_release(self, event):
        self.x1 = event.xdata
        self.y1 = event.ydata
        
        self._ax.figure.canvas.mpl_disconnect(self._op)
        self._ax.figure.canvas.mpl_disconnect(self._or)
        
        # Width and height of rectangle
        dx = abs(self.x1 - self.x0)
        dy = abs(self.y1 - self.y0)
        
        # Find lower left corner of rectangle
        lx = self.x0 if self.x0 < self.x1 else self.x1
        ly = self.y0 if self.y0 < self.y1 else self.y1
        
        # Lower-left
        ll = (lx, ly)
        
        # Upper right
        ur = (lx + dx, ly + dy)
    
        origin = (self.x0, self.y0)
        rect = Rectangle(ll, dx, dy, fc='none', ec='k')
        
        self._ax.add_patch(rect)
        self._ax.figure.canvas.draw()
        
        # Figure out what these values translate to.
        
        # Get basic info about plot
        x = self.plot_info['x']
        y = self.plot_info['y']
        z = self.plot_info['z']
        take_log = self.plot_info['log']
        multiplier = self.plot_info['multiplier']
        
        pars = [x, y]
        
        # Index corresponding to this redshift
        iz = self.blob_redshifts.index(z)
        
        # Use slice routine!
        constraints = \
        {
         x: [z, lambda xx: 1 if lx <= xx <= (lx + dx) else 0],
         y: [z, lambda yy: 1 if ly <= yy <= (ly + dy) else 0],
        }
        
        i = 0
        while hasattr(self, 'slice_%i' % i):
            i += 1
        
        tmp = self._slice_by_nu(pars=pars, z=z, like=0.95, 
            take_log=take_log, **constraints)
        
        setattr(self, 'slice_%i' % i, tmp)        
        
        print "Saved result to slice_%i attribute." % i
        
    def Dump(self, prefix, modelset):
        pass
        
    def ReRunModels(self, prefix=None, N=None, models=None, plot=False, 
        **kwargs):
        """
        Take list of dictionaries and re-run each as a Global21cm model.
        
        Parameters
        ----------
        N : int
            Draw N random samples from chain, and re-run those models.
        
        prefix : str
            Prefix of files to be saved. There will be two:
                i) prefix.chain.pkl
                ii) prefix.blobs.pkl
        
        
        Returns
        -------
        
        
        """
        
        if N is not None:
            model_num = np.arange(N)
            np.random.shuffle(model_num)
            
            models = []
            for i in model_num:
                models.append(self.chain[i,:])
        
        f = open('%s.pinfo.pkl' % prefix, 'wb')
        pickle.dump((self.parameters, self.is_log), f)
        f.close()
        
        pb = ProgressBar(len(models))
        pb.start()
        
        logL = []
        chain = []
        blobs = []
        for i, model in enumerate(models):
            if self.base_kwargs is not None:
                p = self.base_kwargs.copy()
            else:
                p = {}
                
            p.update(kwargs)
            
            if type(model) is dict:
                p.update(model)
            else:
                p.update(self.link_to_dict(model))    
            
            try:
                sim = sG21(**p)
                sim.run()
            except SystemExit:
                pass
                
            if i == 0:
                f = open('%s.binfo.pkl' % prefix, 'wb')
                pickle.dump((sim.blob_names, sim.blob_redshifts), f)
                f.close()
            
            pb.update(i)
            
            blobs.append(sim.blobs)
            chain.append(self.chain[model_num[i],:])
            #logL.append(self.logL[model_num[i],:])
            
            #anl = aG21(sim)
            #
            #if plot:
            #    ax = anl.GlobalSignature(ax=ax, **kwargs)
            #
            #anl_inst.append(anl)
        
        pb.finish()       
                
        f = open('%s.blobs.pkl' % prefix, 'wb')
        pickle.dump(blobs, f)
        f.close()
        
        f = open('%s.chain.pkl' % prefix, 'wb')
        pickle.dump(chain, f)
        f.close()
        
        #f = open('%s.logL.pkl' % prefix, 'wb')
        #pickle.dump(logL, f)
        #f.close()            

        #return ax, anl_inst

    @property
    def plot_info(self):
        if not hasattr(self, '_plot_info'):
            self._plot_info = None
        
        return self._plot_info
        
    @plot_info.setter
    def plot_info(self, value):
        self._plot_info = value

    def sort_by_Tmin(self):
        """
        If doing a multi-pop fit, re-assign population ID numbers in 
        order of increasing Tmin.
        
        Doesn't return anything. Replaces attribute 'chain' with new array.
        """

        # Determine number of populations
        tmp_pf = {key : None for key in self.parameters}
        Npops = count_populations(**tmp_pf)

        if Npops == 1:
            return
        
        # Check to see if Tmin is common among all populations or not    
    
    
        # Determine which indices correspond to Tmin, and population #
    
        i_Tmin = []
        
        # Determine which indices 
        pops = [[] for i in range(Npops)]
        for i, par in enumerate(self.parameters):

            # which pop?
            m = re.search(r"\{([0-9])\}", par)

            if m is None:
                continue

            num = int(m.group(1))
            prefix = par.split(m.group(0))[0]
            
            if prefix == 'Tmin':
                i_Tmin.append(i)

        self._unsorted_chain = self.chain.copy()

        # Otherwise, proceed to re-sort data
        tmp_chain = np.zeros_like(self.chain)
        for i in range(self.chain.shape[0]):

            # Pull out values of Tmin
            Tmin = [self.chain[i,j] for j in i_Tmin]
            
            # If ordering is OK, move on to next link in the chain
            if np.all(np.diff(Tmin) > 0):
                tmp_chain[i,:] = self.chain[i,:].copy()
                continue

            # Otherwise, we need to fix some stuff

            # Determine proper ordering of Tmin indices
            i_Tasc = np.argsort(Tmin)
            
            # Loop over populations, and correct parameter values
            tmp_pars = np.zeros(len(self.parameters))
            for k, par in enumerate(self.parameters):
                
                # which pop?
                m = re.search(r"\{([0-9])\}", par)

                if m is None:
                    tmp_pars.append()
                    continue

                pop_num = int(m.group(1))
                prefix = par.split(m.group(0))[0]
                
                new_pop_num = i_Tasc[pop_num]
                
                new_loc = self.parameters.index('%s{%i}' % (prefix, new_pop_num))
                
                tmp_pars[new_loc] = self.chain[i,k]

            tmp_chain[i,:] = tmp_pars.copy()
                        
        del self.chain
        self.chain = tmp_chain

    @property
    def cosm(self):
        if not hasattr(self, '_cosm'):
            self._cosm = Cosmology()
        
        return self._cosm

    @property
    def derived_blob_names(self):
        if hasattr(self, '_derived_blob_names'):
            return self._derived_blob_names
            
        dbs = self.derived_blobs
        
        return self._derived_blob_names

    @property
    def derived_blobs(self):
        """
        Total rates, convert to rate coefficients.
        """

        if hasattr(self, '_derived_blobs'):
            return self._derived_blobs

        if not hasattr(self, 'blobs'):
            return   

        # Just a dummy class
        pf = ModelSubSet()
        pf.Npops = self.Npops

        # Create data container to mimic that of a single run,
        dqs = []
        self._derived_blob_names = []
        for i, redshift in enumerate(self.blob_redshifts):

            if type(redshift) is str:
                z = self.extract_blob('z', redshift)[i] 
            else:
                z = redshift
                
            data = {}
            data['z'] = np.array([z])
            
            for j, key in enumerate(self.blob_names):
                data[key] = self.blobs[:,i,j]
                            
            _dq = DQ(data, pf)
            
            dqs.append(_dq.derived_quantities.copy())

            for key in _dq.derived_quantities:
                if key in self._derived_blob_names:
                    continue
                
                self._derived_blob_names.append(key)

        # (Nlinks, Nz, Nblobs)
        shape = list(self.blobs.shape[:-1])
        shape.append(len(self._derived_blob_names))

        self._derived_blobs = np.ones(shape) * np.inf
        
        for i, redshift in enumerate(self.blob_redshifts):
            
            data = dqs[i]
            for key in data:
                j = self._derived_blob_names.index(key)
                self._derived_blobs[:,i,j] = data[key]

                
        mask = np.zeros_like(self._derived_blobs)    
        mask[np.isinf(self._derived_blobs)] = 1
        
        self.dmask = mask
        
        self._derived_blobs = np.ma.masked_array(self._derived_blobs, 
            mask=mask)

        return self._derived_blobs

    def set_constraint(self, add_constraint=False, **constraints):
        """
        For ModelGrid calculations, the likelihood must be supplied 
        after-the-fact.

        Parameters
        ----------
        add_constraint: bool
            If True, operate with logical and when constructing likelihood.
            That is, this constraint will be applied in conjunction with
            previous constraints supplied.
        constraints : dict
            Constraints to use in calculating logL
            
        Example
        -------
        # Assume redshift of turning pt. D is 15 +/- 2 (1-sigma Gaussian)
        data = {'z': ['D', lambda x: np.exp(-(x - 15)**2 / 2. / 2.**2)]}
        self.set_constraint(**data)
            
        Returns
        -------
        Sets "logL" attribute, which is used by several routines.    
            
        """    

        if add_constraint and hasattr(self, 'logL'):
            pass
        else:    
            self.logL = np.zeros(self.chain.shape[0])

        if hasattr(self, '_weights'):
            del self._weights

        for i in range(self.chain.shape[0]):
            logL = 0.0
            
            if i >= self.blobs.shape[0]:
                break
            
            for element in constraints:

                z, func = constraints[element]

                j = self.blob_redshifts.index(z)
                if element in self.blob_names:
                    k = self.blob_names.index(element)
                    data = self.blobs[i,j,k]
                else:
                    k = self.derived_blob_names.index(element)
                    data = self.derived_blobs[i,j,k]                

                logL -= np.log(func(data))

            self.logL[i] -= logL

        mask = np.isnan(self.logL)

        self.logL[mask] = -np.inf 

    def Scatter(self, x, y, z=None, c=None, ax=None, fig=1, 
        take_log=False, multiplier=1., labels=None, **kwargs):
        """
        Show occurrences of turning points B, C, and D for all models in
        (z, dTb) space, with points color-coded to likelihood.
    
        Parameters
        ----------
        x : str
            Fields for the x-axis.
        y : str
            Fields for the y-axis.        
        z : str, float
            Redshift at which to plot x vs. y, if applicable.
        c : str
            Field for (optional) color axis.

        Returns
        -------
        matplotlib.axes._subplots.AxesSubplot instance.

        """

        if ax is None:
            gotax = False
            fig = pl.figure(fig)
            ax = fig.add_subplot(111)
        else:
            gotax = True

        if labels is None:
            labels = default_labels
        else:
            labels_tmp = default_labels.copy()
            labels_tmp.update(labels)
            labels = labels_tmp

        if type(take_log) == bool:
            take_log = [take_log] * 2
        if type(multiplier) in [int, float]:
            multiplier = [multiplier] * 2

        if z is not None:
            j = self.blob_redshifts.index(z)

        if x in self.parameters:
            xdat = self.chain[:,self.parameters.index(x)]
        else:
            if z is None:
                raise ValueError('Must supply redshift!')
            if x in self.blob_names:
                xdat = self.blobs[:,j,self.blob_names.index(x)]
            else:
                xdat = self.derived_blobs[:,j,self.derived_blob_names.index(x)]
        
        if y in self.parameters:
            ydat = self.chain[:,self.parameters.index(y)]
        else:
            if z is None:
                raise ValueError('Must supply redshift!')
            if y in self.blob_names:
                ydat = self.blobs[:,j,self.blob_names.index(y)]
            else:
                ydat = self.derived_blobs[:,j,self.derived_blob_names.index(y)]
        
        cdat = None
        if c in self.parameters:
            cdat = self.chain[:,self.parameters.index(c)]
        elif c == 'load':
            cdat = self.load
        elif c is None:
            pass
        else:
            if z is None:
                raise ValueError('Must supply redshift!')
            if c in self.blob_names:
                cdat = self.blobs[:,j,self.blob_names.index(c)]
            else:
                cdat = self.derived_blobs[:,j,self.derived_blob_names.index(c)]

        if take_log[0]:
            xdat = np.log10(xdat)
        if take_log[1]:
            ydat = np.log10(ydat)
        if len(take_log) == 3 and cdat is not None:
            if take_log[2]:
                cdat = np.log10(cdat)  

        if hasattr(self, 'weights') and cdat is None:
            scat = ax.scatter(xdat, ydat, c=self.weights, **kwargs)
        elif cdat is not None:
            scat = ax.scatter(xdat, ydat, c=cdat, **kwargs)
        else:
            scat = ax.scatter(xdat, ydat, **kwargs)

        if take_log[0]:
            ax.set_xlabel(logify_str(labels[self.get_par_prefix(x)]))
        else:
            ax.set_xlabel(labels[self.get_par_prefix(x)])

        if take_log[1]: 
            ax.set_ylabel(logify_str(labels[self.get_par_prefix(y)]))
        else:
            ax.set_ylabel(labels[self.get_par_prefix(y)])
                            
        if c is not None:
            cb = pl.colorbar(scat)
            try:
                if take_log[2]: 
                    cb.set_label(logify_str(labels[self.get_par_prefix(c)]))
                else:
                    cb.set_label(labels[self.get_par_prefix(c)])
            except IndexError:
                cb.set_label(labels[self.get_par_prefix(c)])
        
            self._cb = cb
        
        pl.draw()
        
        self._ax = ax
        self.plot_info = {'x': x, 'y': y, 'log': take_log, 
            'multiplier': multiplier, 'z': z}
    
        return ax
    
    def get_par_prefix(self, par):
        m = re.search(r"\{([0-9])\}", par)

        if m is None:
            return par

        # Population ID number
        num = int(m.group(1))

        # Pop ID including curly braces
        prefix = par.split(m.group(0))[0]
    
        return prefix
    
    @property
    def weights(self):        
        if (not self.is_mcmc) and hasattr(self, 'logL') \
            and (not hasattr(self, '_weights')):
            self._weights = np.exp(self.logL)

        return self._weights

    def get_levels(self, L, nu=[0.95, 0.68]):
        """
        Return levels corresponding to input nu-values, and assign
        colors to each element of the likelihood.
        """
    
        nu, levels = self.confidence_regions(L, nu=nu)
                                                                      
        return nu, levels
    
    def link_to_dict(self, link):
        pf = {}
        for i, par in enumerate(self.parameters):
            if self.is_log[i]:
                pf[par] = 10**link[i]
            else:
                pf[par] = link[i]
        
        return pf
    
    def get_1d_error(self, par, z=None, bins=20, nu=0.68, take_log=False):
        """
        Compute 1-D error bar for input parameter.
        
        Parameters
        ----------
        par : str
            Name of parameter. 
        bins : int
            Number of bins to use in histogram
        nu : float
            Percent likelihood enclosed by this 1-D error
        
        Returns
        -------
        Tuple, (maximum likelihood value, negative error, positive error).

        """
        
        if par in self.parameters:
            j = self.parameters.index(par)
            to_hist = self.chain[:,j]
        elif (par in self.blob_names) or (par in self.derived_blob_names):
            if z is None:
                raise ValueError('Must supply redshift!')
            
            to_hist = self.extract_blob(par, z=z).compressed()

            if take_log:
                to_hist = np.log10(to_hist)

        hist, bin_edges = \
            np.histogram(to_hist, density=True, bins=bins)

        bc = rebin(bin_edges)

        if to_hist is []:
            return None, (None, None)    

        try:
            mu, sigma = float(bc[hist == hist.max()]), error_1D(bc, hist, nu=nu)
        except ValueError:
            return None, (None, None)

        return mu, np.array(sigma)
        
    def _get_1d_kwargs(self, **kw):
        
        for key in ['labels', 'colors', 'linestyles']:
        
            if key in kw:
                kw.pop(key)

        return kw
        
    def _slice_by_nu(self, pars, z=None, take_log=False, bins=20, like=0.68,
        **constraints):
        """
        Return points in dataset satisfying given confidence contour.
        """
        
        binvec, to_hist, is_log = self._prep_plot(pars, z=z, bins=bins, 
            take_log=take_log)
        
        if not self.is_mcmc:
            self.set_constraint(**constraints)
        
        if not hasattr(self, 'weights'):
            weights = None
        else:
            weights = self.weights
        
        hist, xedges, yedges = \
            np.histogram2d(to_hist[0], to_hist[1], bins=binvec, 
            weights=weights)

        # Recover bin centers
        bc = []
        for i, edges in enumerate([xedges, yedges]):
            bc.append(rebin(edges))
                
        # Determine mapping between likelihood and confidence contours

        # Get likelihood contours (relative to peak) that enclose
        # nu-% of the area
        like, levels = self.get_levels(hist, nu=like)
        
        # Grab data within this contour.
        to_keep = np.zeros(to_hist[0].size)
        
        for i in range(hist.shape[0]):
            for j in range(hist.shape[1]):
                if hist[i,j] < levels[0]:
                    continue
                    
                # This point is good
                iok = np.logical_and(xedges[i] <= to_hist[0], 
                    to_hist[0] <= xedges[i+1])
                jok = np.logical_and(yedges[j] <= to_hist[1], 
                    to_hist[1] <= yedges[j+1])
                                    
                ok = iok * jok                    
                                                            
                to_keep[ok == 1] = 1
                
        model_set = ModelSubSet()
        model_set.chain = np.array(self.chain[to_keep == 1])
        model_set.base_kwargs = self.base_kwargs.copy()
        model_set.fails = []
        model_set.blobs = np.array(self.blobs[to_keep == 1,:,:])
        model_set.blob_names = self.blob_names
        model_set.blob_redshifts = self.blob_redshifts
        model_set.is_log = self.is_log
        model_set.parameters = self.parameters
        
        model_set.is_mcmc = self.is_mcmc
        
        if self.is_mcmc:
            model_set.logL = logL[to_keep == 1]
        else:
            model_set.axes = self.axes
        
        return ModelSet(model_set)
        
    def Slice(self, pars=None, z=None, like=0.68, take_log=False, bins=20, 
        **constraints):
        """
        Return revised ("sliced") dataset given set of criteria.
                
        Parameters
        ----------
        like : float
            If supplied, return a new ModelSet instance containing only the
            models with likelihood's exceeding this value.
        constraints : dict
            Dictionary of constraints to use to calculate likelihood.
            Each entry should be a two-element list, with the first
            element being the redshift at which to apply the constraint,
            and second, a function for the posterior PDF for that quantity.s
    
            
            
        Examples
        --------
        
        
        Returns
        -------
        Object to be used to initialize a new ModelSet instance.
        
        """

        return self._slice_by_nu(pars, z=z, take_log=take_log, bins=bins, 
            like=like, **constraints)
        
    def ExamineFailures(self, N=1):
        """
        Try to figure out what went wrong with failed models.
        
        Picks a random subset of failed models, plots them, and returns
        the analysis instances associated with each.
        
        Parameters
        ----------
        N : int
            Number of failed models to plot.
            
        """    
        
        kw = self.base_kwargs.copy()
                
        Nf = len(self.fails)
        
        r = np.arange(Nf)
        np.random.shuffle(r)
        
        ax = None
        objects = {}
        for i in range(N):
            
            idnum = r[i]
            
            p = self.base_kwargs.copy()
            p.update(self.fails[idnum])
            
            sim = sG21(**p)
            sim.run()
            
            anl = aG21(sim)
            ax = anl.GlobalSignature(label='fail i=%i' % idnum)
            
            objects[idnum] = anl
            
        return ax, objects
        
    def _prep_plot(self, pars, z=None, take_log=False, multiplier=1.,
        skip=0, skim=1, bins=20):
        """
        Given parameter names as strings, return data, bins, and log info.
        
        Returns
        -------
        Tuple : (bin vectors, data to histogram, is_log)
        """
        
        if type(pars) not in [list, tuple]:
            pars = [pars]
        if type(take_log) == bool:
            take_log = [take_log] * len(pars)
        if type(multiplier) in [int, float]:
            multiplier = [multiplier] * len(pars)    
        
        if type(z) is list:
            if len(z) != len(pars):
                raise ValueError('Length of z must be = length of pars!')
        else:
            z = [z] * len(pars)
        
        binvec = []
        to_hist = []
        is_log = []
        for k, par in enumerate(pars):

            if par in self.parameters:        
                j = self.parameters.index(par)
                is_log.append(self.is_log[j])
                
                val = self.chain[skip:,j].ravel()[::skim]
                                
                if self.is_log[j]:
                    val += np.log10(multiplier[k])
                else:
                    val *= multiplier[k]
                                
                if take_log[k] and not self.is_log[j]:
                    to_hist.append(np.log10(val))
                else:
                    to_hist.append(val)
                
            elif (par in self.blob_names) or (par in self.derived_blob_names):
                
                if z is None:
                    raise ValueError('Must supply redshift!')
                    
                i = self.blob_redshifts.index(z[k])
                
                if par in self.blob_names:
                    j = list(self.blob_names).index(par)
                else:
                    j = list(self.derived_blob_names).index(par)
                
                is_log.append(False)
                
                if par in self.blob_names:
                    val = self.blobs[skip:,i,j][::skim]
                else:
                    val = self.derived_blobs[skip:,i,j][::skim]
                
                if take_log[k]:
                    val += np.log10(multiplier[k])
                else:
                    val *= multiplier[k]
                
                if take_log[k]:
                    to_hist.append(np.log10(val))
                else:
                    to_hist.append(val)

            else:
                raise ValueError('Unrecognized parameter %s' % str(par))

            # Set bins
            if self.is_mcmc or (par not in self.parameters):
                if type(bins) == int:
                    valc = to_hist[k]
                    binvec.append(np.linspace(valc.min(), valc.max(), bins))
                elif type(bins[k]) == int:
                    valc = to_hist[k]
                    binvec.append(np.linspace(valc.min(), valc.max(), bins[k]))
                else:
                    if take_log[k]:
                        binvec.append(np.log10(bins[k]))
                    else:
                        binvec.append(bins[k])
            else:
                if take_log[k]:
                    binvec.append(np.log10(self.axes[par]))
                else:
                    binvec.append(self.axes[par])
        
        return binvec, to_hist, is_log
               
    def PosteriorPDF(self, pars, z=None, ax=None, fig=1, multiplier=1.,
        nu=[0.95, 0.68], overplot_nu=False, density=True, 
        color_by_like=False, filled=True, take_log=False,
        bins=20, xscale='linear', yscale='linear', skip=0, skim=1, 
        labels=None, **kwargs):
        """
        Compute posterior PDF for supplied parameters. 
    
        If len(pars) == 2, plot 2-D posterior PDFs. If len(pars) == 1, plot
        1-D marginalized PDF.
    
        Parameters
        ----------
        pars : str, list
            Name of parameter or list of parameters to analyze.
        z : float
            Redshift, if any element of pars is a "blob" quantity.
        plot : bool
            Plot PDF?
        nu : float, list
            If plot == False, return the nu-sigma error-bar.
            If color_by_like == True, list of confidence contours to plot.
        color_by_like : bool
            If True, color points based on what confidence contour they lie
            within.
        multiplier : list
            Two-element list of multiplicative factors to apply to elements of
            pars.
        take_log : list
            Two-element list saying whether to histogram the base-10 log of
            each parameter or not.
        skip : int
            Number of steps at beginning of chain to exclude. This is a nice
            way of doing a burn-in after the fact.
        skim : int
            Only take every skim'th step from the chain.

        Returns
        -------
        Either a matplotlib.Axes.axis object or a nu-sigma error-bar, 
        depending on whether we're doing a 2-D posterior PDF (former) or
        1-D marginalized posterior PDF (latter).
    
        """
    
        kw = def_kwargs.copy()
        kw.update(kwargs)
        
        if labels is None:
            labels = default_labels
        else:
            labels_tmp = default_labels.copy()
            labels_tmp.update(labels)
            labels = labels_tmp
        
        if type(pars) not in [list, tuple]:
            pars = [pars]
        if type(take_log) == bool:
            take_log = [take_log] * len(pars)
        if type(multiplier) in [int, float]:
            multiplier = [multiplier] * len(pars)    
        
        if type(z) is list:
            if len(z) != len(pars):
                raise ValueError('Length of z must be = length of pars!')
        else:
            z = [z] * len(pars)
    
        if ax is None:
            gotax = False
            fig = pl.figure(fig)
            ax = fig.add_subplot(111)
        else:
            gotax = True
    
        binvec = []
        to_hist = []
        is_log = []
        for k, par in enumerate(pars):

            if par in self.parameters:        
                j = self.parameters.index(par)
                is_log.append(self.is_log[j])
                
                val = self.chain[skip:,j].ravel()[::skim]
                                
                if self.is_log[j]:
                    val += np.log10(multiplier[k])
                else:
                    val *= multiplier[k]
                                
                if take_log[k] and not self.is_log[j]:
                    to_hist.append(np.log10(val))
                else:
                    to_hist.append(val)
                
            elif (par in self.blob_names) or (par in self.derived_blob_names):
                
                if z is None:
                    raise ValueError('Must supply redshift!')
                    
                i = self.blob_redshifts.index(z[k])
                
                if par in self.blob_names:
                    j = list(self.blob_names).index(par)
                else:
                    j = list(self.derived_blob_names).index(par)
                
                is_log.append(False)
                
                if par in self.blob_names:
                    val = self.blobs[skip:,i,j][::skim]
                else:
                    val = self.derived_blobs[skip:,i,j][::skim]
                
                if take_log[k]:
                    val += np.log10(multiplier[k])
                else:
                    val *= multiplier[k]
                
                if take_log[k]:
                    to_hist.append(np.log10(val))
                else:
                    to_hist.append(val)

            else:
                raise ValueError('Unrecognized parameter %s' % str(par))

            # Set bins
            if self.is_mcmc or (par not in self.parameters):
                if type(bins) == int:
                    valc = to_hist[k]
                    binvec.append(np.linspace(valc.min(), valc.max(), bins))
                elif type(bins[k]) == int:
                    valc = to_hist[k]
                    binvec.append(np.linspace(valc.min(), valc.max(), bins[k]))
                else:
                    if take_log[k]:
                        binvec.append(np.log10(bins[k]))
                    else:
                        binvec.append(bins[k])
            else:
                if take_log[k]:
                    binvec.append(np.log10(self.axes[par]))
                else:
                    binvec.append(self.axes[par])

        if not hasattr(self, 'weights'):
            weights = None
        else:
            weights = self.weights

        if len(pars) == 1:
            
            hist, bin_edges = \
                np.histogram(to_hist[0], density=density, bins=binvec[0], 
                    weights=weights)

            bc = rebin(bin_edges)
        
            tmp = self._get_1d_kwargs(**kw)
            
            ax.plot(bc, hist / hist.max(), drawstyle='steps-mid', **tmp)
            ax.set_xscale(xscale)
            
            if overplot_nu:
                
                try:
                    mu, sigma = bc[hist == hist.max()], error_1D(bc, hist, nu=nu)
                except ValueError:
                    mu, sigma = bc[hist == hist.max()], error_1D(bc, hist, nu=nu[0])
                
                mi, ma = ax.get_ylim()
            
                ax.plot([mu - sigma[0]]*2, [mi, ma], color='k', ls=':')
                ax.plot([mu + sigma[1]]*2, [mi, ma], color='k', ls=':')
            
            ax.set_ylim(0, 1.05)
            
        else:
            
            if to_hist[0].size != to_hist[1].size:
                print 'Looks like calculation was terminated after chain',
                print 'was written to disk, but before blobs. How unlucky!'
                print 'Applying cludge to ensure shape match...'
                
                if to_hist[0].size > to_hist[1].size:
                    to_hist[0] = to_hist[0][0:to_hist[1].size]
                else:
                    to_hist[1] = to_hist[1][0:to_hist[0].size]
                    
            # Compute 2-D histogram
            hist, xedges, yedges = \
                np.histogram2d(to_hist[0], to_hist[1], 
                    bins=[binvec[0], binvec[1]], weights=weights)

            hist = hist.T

            # Recover bin centers
            bc = []
            for i, edges in enumerate([xedges, yedges]):
                bc.append(rebin(edges))
                    
            # Determine mapping between likelihood and confidence contours
            if color_by_like:
    
                # Get likelihood contours (relative to peak) that enclose
                # nu-% of the area
                nu, levels = self.get_levels(hist, nu=nu)
    
                if filled:
                    ax.contourf(bc[0], bc[1], hist / hist.max(), 
                        levels, **kwargs)
                else:
                    ax.contour(bc[0], bc[1], hist / hist.max(),
                        levels, **kwargs)
                
            else:
                if filled:
                    ax.contourf(bc[0], bc[1], hist / hist.max(), **kw)
                else:
                    ax.contour(bc[0], bc[1], hist / hist.max(), **kw)

            if not gotax:
                ax.set_xscale(xscale)
                ax.set_yscale(yscale)
            
            if overplot_nu:
                
                for i in range(2):
                    
                    hist, bin_edges = \
                        np.histogram(to_hist[i], density=density, bins=bins)
                    
                    bc = rebin(bin_edges)
                    
                    mu = bc[hist == hist.max()]
                    
                    try:
                        sigma = error_1D(bc, hist, nu=nu)
                    except ValueError:
                        sigma = error_1D(bc, hist, nu=nu[0])

                    if i == 0:
                        mi, ma = ax.get_ylim()
                    else:
                        mi, ma = ax.get_xlim()

                    if i == 0:
                        ax.plot([mu - sigma[0]]*2, [mi, ma], color='k', ls=':')
                        ax.plot([mu + sigma[1]]*2, [mi, ma], color='k', ls=':')
                    else:
                        ax.plot([mi, ma], [mu - sigma[0]]*2, color='k', ls=':')
                        ax.plot([mi, ma], [mu + sigma[1]]*2, color='k', ls=':')

        self.set_axis_labels(ax, pars, is_log, take_log, labels)

        pl.draw()

        return ax
        
    def ContourScatter(self, x, y, c, z=None, Nscat=1e4, take_log=False, 
        cmap='jet', alpha=1.0, bins=20, vmin=None, vmax=None, zbins=None, 
        labels=None, **kwargs):
        """
        Show contour plot in 2-D plane, and add colored points for third axis.
        
        Parameters
        ----------
        x : str
            Fields for the x-axis.
        y : str
            Fields for the y-axis.
        c : str
            Name of parameter to represent with colored points.
        z : int, float, str
            Redshift (if investigating blobs)
        Nscat : int
            Number of samples plot.
            
        Returns
        -------
        Three objects: the main Axis instance, the scatter plot instance,
        and the colorbar object.
        
        """

        if type(take_log) == bool:
            take_log = [take_log] * 3

        if labels is None:
            labels = default_labels
        else:
            labels_tmp = default_labels.copy()
            labels_tmp.update(labels)
            labels = labels_tmp

        pars = [x, y]

        axes = []
        for par in pars:
            if par in self.parameters:
                axes.append(self.chain[:,self.parameters.index(par)])
            elif par in self.blob_names:
                axes.append(self.blobs[:,self.blob_redshifts.index(z),
                    self.blob_names.index(par)])
            elif par in self.derived_blob_names:
                axes.append(self.derived_blobs[:,self.blob_redshifts.index(z),
                    self.derived_blob_names.index(par)])        

        for i in range(2):
            if take_log[i]:
                axes[i] = np.log10(axes[i])

        xax, yax = axes

        if c in self.parameters:        
            zax = self.chain[:,self.parameters.index(c)].ravel()
        elif c in self.blob_names:   
            zax = self.blobs[:,self.blob_redshifts.index(z),
                self.blob_names.index(c)]
        elif c in self.derived_blob_names:   
            zax = self.derived_blobs[:,self.blob_redshifts.index(z),
                self.derived_blob_names.index(c)]
                
        if zax.shape[0] != self.chain.shape[0]:
            if self.chain.shape[0] > zax.shape[0]:
                xax = xax[0:self.blobs.shape[0]]
                yax = yax[0:self.blobs.shape[0]]
                print 'Looks like calculation was terminated after chain',
                print 'was written to disk, but before blobs. How unlucky!'
                print 'Applying cludge to ensure shape match...'
            else:                
                raise ValueError('Shape mismatch between blobs and chain!')    
                
        if take_log[2]:
            zax = np.log10(zax)    
            
        ax = self.PosteriorPDF(pars, z=z, take_log=take_log, filled=False, 
            bins=bins, **kwargs)
        
        # Pick out Nscat random points to plot
        mask = np.zeros_like(xax, dtype=bool)
        rand = np.arange(len(xax))
        np.random.shuffle(rand)
        mask[rand < Nscat] = True
        
        if zbins is not None:
            cmap_obj = eval('mpl.colorbar.cm.%s' % cmap)
            #if take_log[2]:
            #    norm = mpl.colors.LogNorm(zbins, cmap_obj.N)
            #else:    
            if take_log[2]:
                norm = mpl.colors.BoundaryNorm(np.log10(zbins), cmap_obj.N)
            else:    
                norm = mpl.colors.BoundaryNorm(zbins, cmap_obj.N)
        else:
            norm = None
        
        scat = ax.scatter(xax[mask], yax[mask], c=zax[mask], cmap=cmap,
            zorder=1, edgecolors='none', alpha=alpha, vmin=vmin, vmax=vmax,
            norm=norm)
        cb = pl.colorbar(scat)
        
        cb.set_alpha(1)
        cb.draw_all()

        if c in labels:
            cblab = labels[c]
        elif '{' in c:
            cblab = labels[c[0:c.find('{')]]
        else:
            cblab = c 
            
        cb.set_label(logify_str(cblab))    
            
        cb.update_ticks()
            
        pl.draw()
        
        return ax, scat, cb
        
    def TrianglePlot(self, pars=None, z=None, panel_size=(0.5,0.5), 
        padding=(0,0), show_errors=False, take_log=False, multiplier=1,
        fig=1, inputs={}, tighten_up=0.0, ticks=5, bins=20, mp=None, skip=0, 
        skim=1, top=None, oned=True, filled=True, box=None, rotate_x=True, 
        labels=None, **kwargs):
        """
        Make an NxN panel plot showing 1-D and 2-D posterior PDFs.

        Parameters
        ----------
        pars : list
            Parameters to include in triangle plot.
            1-D PDFs along diagonal will follow provided order of parameters
            from left to right. This list can contain the names of parameters,
            so long as the file prefix.pinfo.pkl exists, otherwise it should
            be the indices where the desired parameters live in the second
            dimension of the MCMC chain.

            NOTE: These can alternatively be the names of arbitrary meta-data
            blobs.

            If None, this will plot *all* parameters, so be careful!

        fig : int
            ID number for plot window.
        bins : int,
            Number of bins in each dimension.
        z : int, float, str, list
            If plotting arbitrary meta-data blobs, must choose a redshift.
            Can be 'B', 'C', or 'D' to extract blobs at 21-cm turning points,
            or simply a number. If it's a list, it must have the same
            length as pars. This is how one can make a triangle plot 
            comparing the same quantities at different redshifts.
        input : dict
            Dictionary of parameter:value pairs representing the input
            values for all model parameters being fit. If supplied, lines
            will be drawn on each panel denoting these values.
        panel_size : list, tuple (2 elements)
            Multiplicative factor in (x, y) to be applied to the default 
            window size as defined in your matplotlibrc file. 
        skip : int
            Number of steps at beginning of chain to exclude. This is a nice
            way of doing a burn-in after the fact.
        skim : int
            Only take every skim'th step from the chain.
        oned : bool    
            Include the 1-D marginalized PDFs?
        filled : bool
            Use filled contours? If False, will use open contours instead.
        color_by_like : bool
            If True, set contour levels by confidence regions enclosing nu-%
            of the likelihood. Set parameter `nu` to modify these levels.
        nu : list
            List of levels, default is 1,2, and 3 sigma contours (i.e., 
            nu=[0.68, 0.95])
        rotate_x : bool
            Rotate xtick labels 90 degrees.
        
        Returns
        -------
        ares.analysis.MultiPlot.MultiPanel instance.
        
        """    
        
        if pars is None:
            pars = self.parameters
        
        kw = def_kwargs.copy()
        kw.update(kwargs)
        
        if labels is None:
            labels = default_labels
        else:
            labels_tmp = default_labels.copy()
            labels_tmp.update(labels)
            labels = labels_tmp
        
        if type(take_log) == bool:
            take_log = [take_log] * len(pars)
        if multiplier == 1:
            multiplier = [multiplier] * len(pars)        
        if type(bins) == int:
            bins = [bins] * len(pars)    
        if type(z) is list:
            if len(z) != len(pars):
                raise ValueError('Length of z must be = length of pars!')
        else:
            z = [z] * len(pars)
        
        is_log = []
        for i, par in enumerate(pars[-1::-1]):
            if par in self.parameters:
                is_log.append(self.is_log[self.parameters.index(par)])
            elif par in self.blob_names or self.derived_blob_names:
                if take_log[-1::-1][i]:
                    is_log.append(True)
                else:    
                    is_log.append(False)
                
        if oned:
            Nd = len(pars)
        else:
            Nd = len(pars) - 1
                           
        # Multipanel instance
        if mp is None:
            mp = MultiPanel(dims=[Nd]*2, padding=padding, diagonal='lower',
                panel_size=panel_size, fig=fig, top=top, **kw)

        # Loop over parameters
        for i, p1 in enumerate(pars[-1::-1]):
            for j, p2 in enumerate(pars):

                # Row number is i
                # Column number is self.Nd-j-1

                k = mp.axis_number(i, j)

                if k is None:
                    continue
                
                if mp.grid[k] is None:
                    continue
                    
                # Input values (optional)
                if inputs:
                        
                    if type(inputs) is list:
                        val = inputs[-1::-1][i]
                    elif p1 in inputs:
                        val = inputs[p1]
                    else:
                        val = None
                                                
                    if val is None:
                        yin = None
                    elif is_log[i]:
                        yin = np.log10(val)                            
                    else:
                        yin = val                        
                else:
                    yin = None
                
                if inputs:
                    
                    if type(inputs) is list:
                        val = inputs[j]        
                    elif p2 in inputs:
                        val = inputs[p2]
                    else:
                        val = None
                    
                    if val is None:
                        xin = None  
                    elif is_log[Nd-j-1]:
                        xin = np.log10(val)
                    else:
                        xin = val

                else:
                    xin = None

                col, row = mp.axis_position(k)    
                                                                                
                # 1-D PDFs on the diagonal    
                if k in mp.diag and oned:

                    self.PosteriorPDF(p1, ax=mp.grid[k], 
                        take_log=take_log[-1::-1][i], z=z[-1::-1][i],
                        multiplier=[multiplier[-1::-1][i]], 
                        bins=[bins[-1::-1][i]], skip=skip, skim=skim, 
                        labels=labels, **kw)

                    if col != 0:
                        mp.grid[k].set_ylabel('')
                    if row != 0:
                        mp.grid[k].set_xlabel('')
                    
                    if show_errors:
                        mu, err = self.get_1d_error(p1)
                                                 
                        mp.grid[k].set_title(err_str(labels[p1], mu, err, 
                            self.is_log[i])) 
                     
                    if not inputs:
                        continue
                        
                    if xin is not None:
                        mp.grid[k].plot([xin]*2, [0, 1.05], 
                            color='k', ls=':', lw=2)
                            
                    continue

                red = [z[j], z[-1::-1][i]]

                # If not oned, may end up with some x vs. x plots
                if p1 == p2 and (red[0] == red[1]):
                    continue

                # 2-D PDFs elsewhere
                self.PosteriorPDF([p2, p1], ax=mp.grid[k], z=red,
                    take_log=[take_log[j], take_log[-1::-1][i]],
                    multiplier=[multiplier[j], multiplier[-1::-1][i]], 
                    bins=[bins[j], bins[-1::-1][i]], filled=filled, 
                    labels=labels, **kw)
                
                if row != 0:
                    mp.grid[k].set_xlabel('')
                if col != 0:
                    mp.grid[k].set_ylabel('')

                # Input values
                if not inputs:
                    continue
                    
                if xin is not None:
                    mp.grid[k].plot([xin]*2, mp.grid[k].get_ylim(), color='k', 
                        ls=':')
                if yin is not None:
                    mp.grid[k].plot(mp.grid[k].get_xlim(), [yin]*2, color='k', 
                        ls=':')

        if oned:
            mp.grid[np.intersect1d(mp.left, mp.top)[0]].set_yticklabels([])
        
        mp.fix_ticks(oned=oned, N=ticks, rotate_x=rotate_x)
        mp.rescale_axes(tighten_up=tighten_up)
    
        return mp
        
    def RedshiftEvolution(self, blob, ax=None, redshifts=None, fig=1,
        nu=0.68, take_log=False, bins=20, label=None, **kwargs):
        """
        Plot constraints on the redshift evolution of given quantity.
        
        Parameters
        ----------
        blob : str
            
        Note
        ----
        If you get a "ValueError: attempt to get argmin of an empty sequence"
        you might consider setting take_log=True.    
            
        """    
        
        if ax is None:
            gotax = False
            fig = pl.figure(fig)
            ax = fig.add_subplot(111)
        else:
            gotax = True

        try:
            ylabel = default_labels[blob]
        except KeyError:
            ylabel = blob
        
        if redshifts is None:
            redshifts = self.blob_redshifts
            
        for i, z in enumerate(redshifts):
            
            if i == 0:
                l = label
            else:
                l = None
            
            try:
                value, (blob_err1, blob_err2) = \
                    self.get_1d_error(blob, z=z, nu=nu, take_log=take_log,
                    bins=bins)
            except TypeError:
                continue
            
            if value is None:
                continue    
            
            # Error on redshift
            if type(z) == str:
                mu_z, (z_err1, z_err2) = \
                    self.get_1d_error('z', z=z, nu=nu, bins=bins)
                xerr = np.array(z_err1, z_err2).T
            else:
                mu_z = z
                xerr = None
            
            ax.errorbar(mu_z, value, 
                xerr=xerr, 
                yerr=np.array(blob_err1, blob_err2).T, 
                lw=2, elinewidth=2, capsize=3, capthick=1, label=l,
                **kwargs)        
        
        # Look for populations
        m = re.search(r"\{([0-9])\}", blob)
        
        if m is None:
            prefix = blob
        else:
            # Population ID number
            num = int(m.group(1))
            
            # Pop ID excluding curly braces
            prefix = blob.split(m.group(0))[0]
        
        ax.set_xlabel(r'$z$')
        ax.set_ylabel(ylabel)
        pl.draw()
        
        return ax
        
    def add_boxes(self, ax=None, val=None, width=None, **kwargs):
        """
        Add boxes to 2-D PDFs.
        
        Parameters
        ----------
        ax : matplotlib.axes._subplots.AxesSubplot instance
        
        val : int, float
            Center of box (probably maximum likelihood value)
        width : int, float
            Size of box (above/below maximum likelihood value)
        
        """
        
        if width is None:
            return
        
        iwidth = 1. / width
            
        # Vertical lines
        ax.plot(np.log10([val[0] * iwidth, val[0] * width]), 
            np.log10([val[1] * width, val[1] * width]), **kwargs)
        ax.plot(np.log10([val[0] * iwidth, val[0] * width]), 
            np.log10([val[1] * iwidth, val[1] * iwidth]), **kwargs)
            
        # Horizontal lines
        ax.plot(np.log10([val[0] * iwidth, val[0] * iwidth]), 
            np.log10([val[1] * iwidth, val[1] * width]), **kwargs)
        ax.plot(np.log10([val[0] * width, val[0] * width]), 
            np.log10([val[1] * iwidth, val[1] * width]), **kwargs)

    def extract_blob(self, name, z):
        """
        Extract a 1-D array of values for a given quantity at a given redshift.
        """
    
        try:
            i = self.blob_redshifts.index(z)
        except ValueError:
            
            ztmp = []
            for redshift in self.blob_redshifts_float:
                if redshift is None:
                    ztmp.append(None)
                else:
                    ztmp.append(round(redshift, 1))    
                
            i = ztmp.index(round(z, 1))
    
        if name in self.blob_names:
            j = self.blob_names.index(name)            
            return self.blobs[:,i,j]
        else:
            j = self.derived_blob_names.index(name)
            return self.derived_blobs[:,i,j]
    
    def max_likelihood_parameters(self):
        """
        Return parameter values at maximum likelihood point.
        """
    
        iML = np.argmax(self.logL)
    
        p = {}
        for i, par in enumerate(self.parameters):
            if self.is_log[i]:
                p[par] = 10**self.chain[iML,i]
            else:
                p[par] = self.chain[iML,i]
    
        return p
        
    def set_axis_labels(self, ax, pars, is_log, take_log=False, labels=None):
        """
        Make nice axis labels.
        """
        
        if labels is None:
            labels = default_labels
        else:
            labels_tmp = default_labels.copy()
            labels_tmp.update(labels)
            labels = labels_tmp
        
        p = []
        sup = []
        for par in pars:
            
            if type(par) is int:
                sup.append(None)
                p.append(par)
                continue
                
            # If we want special labels for population specific parameters
            if par in labels:
                sup.append(None)
                p.append(par)
                continue    
                
            m = re.search(r"\{([0-9])\}", par)
            
            if m is None:
                sup.append(None)
                p.append(par)
                continue
            
            # Split parameter prefix from population ID in braces
            p.append(par.split(m.group(0))[0])
            sup.append(int(m.group(1)))
        
        del pars
        pars = p
    
        if type(take_log) == bool:
            take_log = [take_log] * len(pars)
    
        if pars[0] in labels:
            if is_log[0] or take_log[0]:
                ax.set_xlabel(logify_str(labels[pars[0]]))
            else:
                ax.set_xlabel(labels[pars[0]])
                    
        elif type(pars[0]) == int:
            ax.set_xlabel(def_par_labels(pars[0]))
        else:
            ax.set_xlabel(self.mathify_str(pars[0]))
    
        if len(pars) == 1:
            ax.set_ylabel('PDF')
    
            pl.draw()
            return
    
        if pars[1] in labels:
            if is_log[1] or take_log[1]:
                ax.set_ylabel(logify_str(labels[pars[1]]))
            else:
                ax.set_ylabel(labels[pars[1]])
        elif type(pars[1]) == int:
            ax.set_ylabel(def_par_labels(pars[1]))
        else:
            ax.set_ylabel(self.mathify_str(pars[1]))
        
        pl.draw()
        
    def mathify_str(self, s):
        return r'$%s$' % s    
        
    def confidence_regions(self, L, nu=[0.95, 0.68]):
        """
        Integrate outward at "constant water level" to determine proper
        2-D marginalized confidence regions.
    
        Note: this is fairly crude.
    
        Parameters
        ----------
        L : np.ndarray
            Grid of likelihoods.
        nu : float, list
            Confidence intervals of interest.
    
        Returns
        -------
        List of contour values (relative to maximum likelihood) corresponding 
        to the confidence region bounds specified in the "nu" parameter, 
        in order of decreasing nu.
        """
    
        if type(nu) in [int, float]:
            nu = np.array([nu])
    
        # Put nu-values in ascending order
        if not np.all(np.diff(nu) > 0):
            nu = nu[-1::-1]
    
        peak = float(L.max())
        tot = float(L.sum())
    
        # Counts per bin in descending order
        Ldesc = np.sort(L.ravel())[-1::-1]
    
        j = 0  # corresponds to whatever contour we're on
    
        Lprev = 1.0
        Lencl_prev = 0.0
        contours = [1.0]
        for i in range(1, Ldesc.size):
    
            # How much area (fractional) is enclosed within the current contour?
            Lencl_now = L[L >= Ldesc[i]].sum() / tot
    
            Lnow = Ldesc[i]
    
            # Haven't hit next contour yet
            if Lencl_now < nu[j]:
                pass
    
            # Just passed a contour
            else:
                # Interpolate to find contour more precisely
                Linterp = np.interp(nu[j], [Lencl_prev, Lencl_now],
                    [Ldesc[i-1], Ldesc[i]])
                # Save relative to peak
                contours.append(Linterp / peak)
    
                j += 1
    
            Lprev = Lnow
            Lencl_prev = Lencl_now
    
            if j == len(nu):
                break
    
        # Return values that match up to inputs    
        return nu[-1::-1], contours[-1::-1]
    
    def errors_to_latex(self, pars, nu=0.68, in_units=None, out_units=None):
        """
        Output maximum-likelihood values and nu-sigma errors ~nicely.
        """
                
        if type(nu) != list:
            nu = [nu]
            
        hdr = 'parameter    '
        for conf in nu:
            hdr += '%.1f' % (conf * 100)
            hdr += '%    '
        
        print hdr
        print '-' * len(hdr)    
        
        for i, par in enumerate(pars):
            
            s = str(par)
            
            for j, conf in enumerate(nu):
                
                
                mu, sigma = \
                    map(np.array, self.get_1d_error(par, bins=100, nu=conf))

                if in_units and out_units != None:
                    mu, sigma = self.convert_units(mu, sigma,
                        in_units=in_units, out_units=out_units)

                s += r" & $%5.3g_{-%5.3g}^{+%5.3g}$   " % (mu, sigma[0], sigma[1])
        
            s += '\\\\'
            
            print s
    
    def convert_units(self, mu, sigma, in_units, out_units):
        """
        Convert units on common parameters of interest.
        
        So far, just equipped to handle frequency -> redshift and Kelvin
        to milli-Kelvin conversions. 
        
        Parameters
        ----------
        mu : float
            Maximum likelihood value of some parameter.
        sigma : np.ndarray
            Two-element array containing asymmetric error bar.
        in_units : str
            Units of input mu and sigma values.
        out_units : str
            Desired units for output.
        
        Options
        -------
        in_units and out_units can be one of :
        
            MHz
            redshift
            K
            mK
            
        Returns
        -------
        Tuple, (mu, sigma). Remember that sigma is itself a two-element array.
            
        """
        
        if in_units == 'MHz' and out_units == 'redshift':
            new_mu = nu_0_mhz / mu - 1.
            new_sigma = abs(new_mu - (nu_0_mhz / (mu + sigma[1]) - 1.)), \
                abs(new_mu - (nu_0_mhz / (mu - sigma[0]) - 1.))
                        
        elif in_units == 'redshift' and out_units == 'MHz':
            new_mu = nu_0_mhz / (1. + mu)
            new_sigma = abs(new_mu - (nu_0_mhz / (1. + mu - sigma[0]))), \
                        abs(new_mu - (nu_0_mhz / (1. + mu - sigma[1])))
        elif in_units == 'K' and out_units == 'mK':
            new_mu = mu * 1e3
            new_sigma = np.array(sigma) * 1e3
        elif in_units == 'mK' and out_units == 'K':
            new_mu = mu / 1e3
            new_sigma = np.array(sigma) / 1e3
        else:
            raise ValueError('Unrecognized unit combination')
        
        return new_mu, new_sigma
    