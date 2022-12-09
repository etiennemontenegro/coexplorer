"""
Extension classes enhance TouchDesigner components with python. An
extension is accessed via ext.ExtensionClassName from any operator
within the extended component. If the extension is promoted via its
Promote Extension parameter, all its attributes with capitalized names
can be accessed externally, e.g. op('yourComp').PromotedFunction().

Help: search "Extensions" in wiki
"""

from TDStoreTools import StorageManager
import TDFunctions as TDF

import subprocess 
import sys
import time

osc = op('oscout1')
goodZone = op('good_zone')
badZone = op('bad_zone')
history = op('history')


class coexplorer:
	"""
	coexplorer description
	"""
	def __init__(self, ownerComp):
		# The component to which this extension is attached
		self.ownerComp = ownerComp

		# properties
		TDF.createProperty(self, 'MyProperty', value=0, dependable=True,
						   readOnly=False)


		self.process = None
		

		# stored items (persistent across saves and re-initialization):
		storedItems = [
			# Only 'name' is required...
			{'name': 'StoredProperty', 'default': None, 'readOnly': False,
			 						'property': True, 'dependable': True},
		]
		# Uncomment the line below to store StoredProperty. To clear stored
		# 	items, use the Storage section of the Component Editor
		
		# self.stored = StorageManager(self, ownerComp, storedItems)


	def Launch(self):
		self.clearOutput()
		# point to our script that we're going to execute
		cmd_python_script = '{}/scripts/TheInteractiveAgent_V5.py'.format(project.folder)
		python_exe = parent().par.Pythonexe.val
		name = op.coexplorer.par.Name.eval()
		state = str(op.coexplorer.par.State.val)
		list_arg = ['--name', name , '--state', state]
		command = [python_exe, cmd_python_script] + list_arg
		print(command)
		if self.process == None:
			self.process = subprocess.Popen(command, shell = False)
		elif self.process is not None:
			self.process.kill()
			self.process = subprocess.Popen(command, shell = False)
		self.DisableUI()
		return
	
	def Reinit(self):
		op.launchui.par.Value0 = 0	
		op.explorationui.par.Value0 = 0 
		self.ClearMonitor()
		self.clearOutput()
		self.ClearTables()
		return

	def DisableUI(self):
		parent().par.Enableui = 0
		return
	
	def EnableUI(self):
		parent().par.Enableui = 1
		return

	def Kill(self):
		self.process.kill()
		self.process = None
		op.explorationui.par.Value0 = 0 
		return
	
	def Stop(self):
		osc.sendOSC("/stop",[0])
		op.explorationui.par.Value0 = 0 
		return
		

	def GetPid(self):#useful??
		print(self.process.pid)
		return

	def clearOutput(self):
		op.osc.par.Clear.pulse()
		return
		
	def Direction(self , reward):
		if reward == True:
			osc.sendOSC("/direction",[1])
			self.storeDirection(1)
		elif reward == False:
			osc.sendOSC("/direction",[-1])
			self.storeDirection(-1)
		return
		
	def Zone(self , reward):
		if reward == True:
			osc.sendOSC("/zone",[1])
		elif reward == False:
			osc.sendOSC("/zone",[-1])
		return
			
	def Resample(self , dir ):
		print("precision")	
		if dir :
			osc.sendOSC("/resample",[1])
		else:
			osc.sendOSC("/resample",[-1])
		return
	
	def Speed(self, dir):	
		print("speed")
		if dir:
			osc.sendOSC("/speed",[1])
		else:
			osc.sendOSC("/speed",[-1])
		return
	
	def Save(self):
		#path = ui.chooseFile(load=False,fileTypes=['.ckpt'])
		path = ui.chooseFile(load=False, fileTypes=[''])
		osc.sendOSC("/save",["symbol",path])

		self.saveToText(goodZone,path,"good_zones")
		self.saveToText(badZone,path,"bad_zones")
		self.saveTrail(path)
		return
	
	def saveTrail(self,path):
		full_path = path + "_trail.chan"
		op.monitor.op('trail1').save(full_path)
		return

	def saveToText(self,op,path,name):
		full_path = path +"_"+ name + '.csv'
		op.save(full_path)
		return

	def Load(self):
		path = ui.chooseFile(title='Select model to load')
		path_no_ext = path.split('.')[0].split('-')[0]
		path_good = path_no_ext+"_good_zones.csv"
		path_bad = path_no_ext+"_bad_zones.csv"
		goodZone.par.file = path_good
		time.sleep(0.1)
		badZone.par.file = path_bad
		osc.sendOSC("/load",[path])
		return
	
	def Reset(self):
		osc.sendOSC("/reset",[1])
		return
	
	def ExploreState(self):
		print('explore')
		osc.sendOSC("/explore_state",[1])
		return
	
	def ExploreAction(self):
		osc.sendOSC("/explore_action",[1])
		return
	
	def State(self, dir):
		print("State")
		if dir:
			osc.sendOSC("/next_state",[1])
		else:
			osc.sendOSC("/previous_state",[1])
		return
	
	def AutoExplore(self, io):
		osc.sendOSC("/autoexplore",[int(not(io))])	
		self.SendState()
		return
	
	def GetState(self):
		state = list()
		for page in parent().customPages:
			if page.name == "State":
				for p in page:
					state.append(p.val)
		return state
	
	def SendState(self):
		state = list()
		for page in parent().customPages:
			if page.name == "State":
				for p in page:
					state.append(p.val)
					

		osc.sendOSC("/sample_vst",state)
		return

	def Overridebcf(self):
		state = list()
		idx = 0
		for page in parent().customPages:
			if page.name == "State":
				for p in page:
					op.bcf.OverrideFader(idx,p.val)
					idx = idx +1
					

		osc.sendOSC("/sample_vst",state)
		return

	def SetState(self,state):
		i =0
		max_idx = len(state)
		for page in parent().customPages:
			if page.name == "State":
				for p in page:

					p.val = state[i]
					i = i+1
					if i >= max_idx:
						break
		return


	def ClearMonitor(self):
		op.monitor.par.Clear.pulse()
		return

	def ClearTables(self):
		goodZone.clear()
		badZone.clear()
		history.clear()
		return

	def StoreGoodZone(self, state):
		state.insert(0," ")
		goodZone.appendRow(state)
		return
		
	def StoreBadZone(self, state):
		state.insert(0," ")
		badZone.appendRow(state)
		return
		
	def storeDirection(self,dir):
		state = self.GetState()
		state.insert(0, dir)
		state.insert(0 , op.osc.op('oscin3')[0])
		state.insert(0 ," ")
		history.appendRow(state)
		return
