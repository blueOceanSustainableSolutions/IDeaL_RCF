from ideal_rcf.dataloader.caseset import CaseSet

from typing import Optional, List
from pathlib import Path
import numpy as np
import re
import os

### load files from results
### S_final
### U
### wallShearStress

class FoamLoader(object):
    def __init__(self,
                 caseset :CaseSet):
        
        if not isinstance(caseset, CaseSet):
            raise AssertionError(f'[config_error] base_model_config must be of instance {CaseSet()}')

        self.caseset = caseset


    def read_U_from_foam(self,
                         dir_path :Path,
                         _id :Optional[str]='predictions',
                         dump :Optional[bool]=False):
        
        with open(f'{dir_path}/U') as f:
            foam_file = f.readlines()
        n_points = int(foam_file[21])
        _U = foam_file[23:23+n_points]
        U_mag = np.array([np.linalg.norm([float(ent) for ent in re.findall(r"[-+]?(?:\d*\.?\d+)(?:[eE][-+]?\d+)?", entry)][:2]) for entry in _U])
        U_vec = np.array([np.array([float(ent) for ent in re.findall(r"[-+]?(?:\d*\.?\d+)(?:[eE][-+]?\d+)?", entry)][:2]) for entry in _U])
        
        setattr(self.caseset, f'{_id}_u', U_vec[:,0])
        setattr(self.caseset, f'{_id}_v', U_vec[:,1])
        setattr(self.caseset, f'{_id}_U', U_mag)
        return  U_mag, U_vec if dump else None


    def read_WSS_from_foam(self,
                            dir_path :Path,
                            _id :Optional[str]='predictions',
                           dump :Optional[bool]=False):
        
        with open(f'{dir_path}/wallShearStress') as f:
            foam_file = f.readlines()
        n_points = int(foam_file[28])
        _WSS = foam_file[30:30+n_points]
        WSS = np.array([np.array([float(ent) for ent in re.findall(r"[-+]?(?:\d*\.?\d+)(?:[eE][-+]?\d+)?", entry)][0]) for entry in _WSS])
        
        setattr(self.caseset, f'{_id}_wss', WSS)
        return WSS if dump else None


    def read_from_dir(self,
                      dir_path :Path):
        
        results_path = f'{dir_path}/results'  
        if not os.path.exists(results_path):
            raise FileNotFoundError(f'Make sure results_path exists and contains the resulting fields generated by openfoam')
        
        self.read_U_from_foam(results_path)

        rans_path = f'{dir_path}/rans'
        if os.path.exists(rans_path):
            self.read_U_from_foam(rans_path, 'rans')


class extract_U_profiles(object):
    def __init__(self, 
                 caseset_obj :CaseSet,
                 nX=99,
                 nY=149,
                 velocities :List[str]=['rans', 'predictions', 'dns']):
        
        self.index_to_extract = [i for i in range(5,99,8)][1:]
        self.caseset_obj = caseset_obj
        self.profiles = velocities
        self.U_mean = np.mean([np.linalg.norm([u, v]) for u,v in zip(getattr(caseset_obj,f'u')[:,0], getattr(caseset_obj,f'v')[:,0])])
        self.nX = nX
        self.nY = nY


    def extract_profile(self, U):
        profile_dict = {}
        for index in self.index_to_extract:
            comp_dict = {}
            for j, comp in enumerate(['u', 'v']):
                comp_dict[comp] = np.array(
                    [
                        [
                            self.caseset_obj.Cx[i][0]+2/3*U[i,j]/self.U_mean, self.caseset_obj.Cy[i][0]
                        ] for i in range(index, self.nX*self.nY, self.nX)
                    ]
                )
            profile_dict[self.caseset_obj.Cx[index][0]] = comp_dict

        return profile_dict


    def get_profiles(self):
        profiles_dict = {}
        for profile in self.profiles:
            if profile != 'dns':
                U = np.array([[u,v] for u,v in zip(getattr(self.caseset_obj, f'{profile}_u'), getattr(self.caseset_obj, f'{profile}_v'))])
            else:
                U = np.array([[u,v] for u,v in zip(getattr(self.caseset_obj, f'u')[:,0], getattr(self.caseset_obj, f'v')[:,0])])

            profiles_dict[profile] = self.extract_profile(U)

        return profiles_dict
    

class ODE_operator(object):
    def __init__(self,
                 caseset_obj :CaseSet,
                 scalar_attr :str,
                 nX=99, nY=149):
        
        self.X = caseset_obj.Cx[:,0]
        self.Y = caseset_obj.Cy[:,0]
        self.nY = nY
        self.nX = nX
        self.a = getattr(caseset_obj, scalar_attr)
        if scalar_attr == 'u':
            self.a = self.a[:,0]
        
        self.interior_points = self.assemble_index()
        
        self.dX, self.dY = self.build_distance_matrix_interior_points()
        
        self.build_boundary_distances()


    def inlet(self):
        return np.array([(i+1)*self.nX-1 for i in range(self.nY)])          


    def outlet(self):
        return np.array([i*self.nX for i in range(self.nY)])


    def top(self):
        return np.array([i for i in range(self.nX)])    


    def wall(self):
        return np.array([len(self.X)-i for i in range(1,self.nX+1)])  


    def assemble_index(self): 
        BCs = np.unique(np.concatenate((self.top(), self.wall(), self.outlet(), self.inlet()), axis = None))
        interior_points = np.array([i for i in range(len(self.X)) if i not in BCs])
        return interior_points


    def build_distance_matrix_interior_points(self):
        dX = np.array([0.0 for i in range(len(self.X))])
        dY = np.array([0.0 for i in range(len(self.Y))])
        for j in range(self.nY):
            for i in range(self.nX):
                if 0<i<self.nX-1:
                    dX[j*self.nX+i] = self.X[j*self.nX+i-1] - self.X[j*self.nX+i+1]
                if 0<j<self.nY-1: 
                    dY[j*self.nX+i] = self.Y[(j-1)*self.nX+i] - self.Y[(j+1)*self.nX+i]
        return dX, dY


    def build_boundary_distances(self):
        ### 0 nX - 1
        ### -1 -nX
        for j in range(self.nY):
            ### outlet
            self.dX[j*self.nX] = self.X[j*self.nX]-self.X[j*self.nX+1]
            ### inlet
            self.dX[(j+1)*self.nX-1] = -self.X[(j+1)*self.nX-1]+self.X[(j+1)*self.nX-2] 
        
        for i in range(self.nX+1):
            ### top
            self.dY[i] =  self.Y[i] - self.Y[i+self.nX]
            ### bottom
            if i > 0:
                self.dY[-i] = -self.Y[-i] + self.Y[-i-self.nX]


    def extract_WSS(self, viscosity=5e-6,index_dict=None):

        top_WSS = np.array([0.0 for i in range(len(self.X))])
        bottom_WSS = np.array([0.0 for i in range(len(self.X))])

        for i in range(self.nX+1):
            ### top
            top_WSS[i] += (0-self.a[i])/self.dY[i]*0.5 ### d(a_12)/d(y)
            #top_WSS[i] += (self.a[i+self.nX][2] - self.a[i+self.nX][2])/self.dY[i] ### d(a_22)/d(y)
            
            ### bottom
            if i > 0:
                bottom_WSS[-i] += (self.a[-i]-0)/np.sqrt(np.square(self.dY[-i]*0.5)+np.square(np.abs(self.X[i]-self.X[i-self.nX]))) ### d(a_12)/d(y)
                #bottom_WSS[-i] += (self.a[-i][2] - self.a[-i-self.nX][2])/self.dY[-i] ### d(a_22)/d(y)
        if index_dict:
            return {'top':  viscosity*top_WSS[index_dict['start']:index_dict['end']],
                    'bottom':  viscosity*bottom_WSS[index_dict['start']:index_dict['end']]}
        else:
            return {'top': viscosity*top_WSS,
                    'bottom': viscosity*bottom_WSS}


    def check_continuity(self):
        continuity_solution = np.array([0.0 for i in range(len(self.X))])
        print('> Checking continuity of the provided field')
        ### loop over interior points
        for j in range(self.nY):
            for i in range(self.nX):
                if 0<i<self.nX-1:
                    continuity_solution[j*self.nX+i] += (self.a[j*self.nX+i-1][0] - self.a[j*self.nX+i+1][0])/self.dX[j*self.nX+i] ### d(a_11)/d(x)
                    continuity_solution[j*self.nX+i] += (self.a[j*self.nX+i-1][1] - self.a[j*self.nX+i+1][1])/self.dX[j*self.nX+i] ### d(a_12)/d(x)
                    
                if 0<j<self.nY-1: 
                    continuity_solution[j*self.nX+i] += (self.a[(j-1)*self.nX+i][1] - self.a[(j+1)*self.nX+i][1])/self.dY[j*self.nX+i] ### d(a_12)/d(y)
                    continuity_solution[j*self.nX+i] += (self.a[(j-1)*self.nX+i][2] - self.a[(j+1)*self.nX+i][2])/self.dY[j*self.nX+i] ### d(a_22)/d(y)
                    
        ### loop over BCs
        for j in range(self.nY):
            ### outlet
            continuity_solution[j*self.nX] += (self.a[j*self.nX][0] - self.a[j*self.nX+1][0])/self.dX[j*self.nX] ### d(a_11)/d(x)
            continuity_solution[j*self.nX] += (self.a[j*self.nX][1] - self.a[j*self.nX+1][1])/self.dX[j*self.nX] ### d(a_12)/d(x)
            
            ### inlet
            continuity_solution[(j+1)*self.nX-1] += (self.a[(j+1)*self.nX-1][0] - self.a[(j+1)*self.nX-2][0])/self.dY[j*self.nX+i] ### d(a_11)/d(x)
            continuity_solution[(j+1)*self.nX-1] += (self.a[(j+1)*self.nX-1][1] - self.a[(j+1)*self.nX-2][1])/self.dY[j*self.nX+i] ### d(a_12)/d(x)
        
        for i in range(self.nX+1):
            ### top
            continuity_solution[i] += (self.a[i+self.nX][1] - self.a[i+self.nX][1])/self.dY[i] ### d(a_12)/d(y)
            continuity_solution[i] += (self.a[i+self.nX][2] - self.a[i+self.nX][2])/self.dY[i] ### d(a_22)/d(y)
            
            ### bottom
            if i > 0:
                continuity_solution[-i] += (self.a[-i][1] - self.a[-i-self.nX][1])/self.dY[-i] ### d(a_12)/d(y)
                continuity_solution[-i] += (self.a[-i][2] - self.a[-i-self.nX][2])/self.dY[-i] ### d(a_22)/d(y)
                            
        return continuity_solution


    def calculate_distances(self):
        
        return np.concatenate((self.X[self.top()], self.X[self.wall()], self.X[self.outlet()], self.X[self.inlet()]), axis=None), np.concatenate((self.Y[self.top()], self.Y[self.wall()], self.Y[self.outlet()], self.Y[self.inlet()]), axis=None) 