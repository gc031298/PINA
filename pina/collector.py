from .utils import check_consistency, merge_tensors

class Collector:
    def __init__(self, problem):
        self.problem = problem                                                  # hook Collector <-> Problem
        self.data_collections = {name : {} for name in self.problem.conditions} # collection of data
        self.is_conditions_ready = {
            name : False for name in self.problem.conditions}                   # names of the conditions that need to be sampled
        self.full = False                                                       # collector full, all points for all conditions are given and the data are ready to be used in trainig
        
    @property
    def full(self):
        return all(self.is_conditions_ready.values())
    
    @full.setter
    def full(self, value):
        check_consistency(value, bool)
        self._full = value

    @property
    def problem(self):
        return self._problem
    
    @problem.setter
    def problem(self, value):
        self._problem = value

    def store_fixed_data(self):
        # loop over all conditions
        for condition_name, condition in self.problem.conditions.items():
            # if the condition is not ready and domain is not attribute
            # of condition, we get and store the data
            if (not self.is_conditions_ready[condition_name]) and (not hasattr(condition, "domain")):
                # get data
                keys = condition.__slots__
                values = [getattr(condition, name) for name in keys]
                self.data_collections[condition_name] = dict(zip(keys, values))
                # condition now is ready
                self.is_conditions_ready[condition_name] = True

    def store_sample_domains(self, n, mode, variables, sample_locations):
        # loop over all locations
        for loc in sample_locations:
            # get condition
            condition = self.problem.conditions[loc]
            keys = ["input_points", "equation"]
            # if the condition is not ready, we get and store the data
            if (not self.is_conditions_ready[loc]):
                # if it is the first time we sample
                if not self.data_collections[loc]:
                    already_sampled = []
                # if we have sampled the condition but not all variables
                else:
                    already_sampled = [self.data_collections[loc].input_points]
            # if the condition is ready but we want to sample again
            else:
                self.is_conditions_ready[loc] = False
                already_sampled = []

            # get the samples
            samples = [
                condition.domain.sample(n=n, mode=mode, variables=variables)
            ] + already_sampled
            pts = merge_tensors(samples)
            if (
                sorted(self.data_collections[loc].input_points.labels) 
                ==
                sorted(self.problem.input_variables)
                ):
                self.is_conditions_ready[loc] = True
                values = [pts, condition.equation]
                self.data_collections[loc] = dict(zip(keys, values))