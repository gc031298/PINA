import torch
import pytest

from pina.problem import SpatialProblem
from pina.operators import nabla
from pina.geometry import CartesianDomain
from pina import Condition, LabelTensor, PINN
from pina.trainer import Trainer
from pina.model import FeedForward
from pina.equation.equation import Equation
from pina.equation.equation_factory import FixedValue
from pina.plotter import Plotter
from pina.loss import LpLoss


def laplace_equation(input_, output_):
    force_term = (torch.sin(input_.extract(['x'])*torch.pi) *
                    torch.sin(input_.extract(['y'])*torch.pi))
    nabla_u = nabla(output_.extract(['u']), input_)
    return nabla_u - force_term

my_laplace = Equation(laplace_equation)
in_ = LabelTensor(torch.tensor([[0., 1.]], requires_grad=True), ['x', 'y'])
out_ = LabelTensor(torch.tensor([[0.]], requires_grad=True), ['u'])

class Poisson(SpatialProblem):
    output_variables = ['u']
    spatial_domain = CartesianDomain({'x': [0, 1], 'y': [0, 1]})

    conditions = {
        'gamma1': Condition(
            location=CartesianDomain({'x': [0, 1], 'y':  1}),
            equation=FixedValue(0.0)),
        'gamma2': Condition(
            location=CartesianDomain({'x': [0, 1], 'y': 0}),
            equation=FixedValue(0.0)),
        'gamma3': Condition(
            location=CartesianDomain({'x':  1, 'y': [0, 1]}),
            equation=FixedValue(0.0)),
        'gamma4': Condition(
            location=CartesianDomain({'x': 0, 'y': [0, 1]}),
            equation=FixedValue(0.0)),
        'D': Condition(
            location=CartesianDomain({'x': [0, 1], 'y': [0, 1]}),
            equation=my_laplace),
        'data': Condition(
            input_points=in_,
            output_points=out_)
    }

    def poisson_sol(self, pts):
        return -(
            torch.sin(pts.extract(['x'])*torch.pi) *
            torch.sin(pts.extract(['y'])*torch.pi)
        )/(2*torch.pi**2)

    truth_solution = poisson_sol


class myFeature(torch.nn.Module):
    """
    Feature: sin(x)
    """

    def __init__(self):
        super(myFeature, self).__init__()

    def forward(self, x):
        t = (torch.sin(x.extract(['x'])*torch.pi) *
             torch.sin(x.extract(['y'])*torch.pi))
        return LabelTensor(t, ['sin(x)sin(y)'])


# make the problem
poisson_problem = Poisson()
model = FeedForward(len(poisson_problem.input_variables),len(poisson_problem.output_variables))
model_extra_feats = FeedForward(len(poisson_problem.input_variables)+1,len(poisson_problem.output_variables))
extra_feats = [myFeature()]


def test_constructor():
    PINN(problem = poisson_problem, model=model, extra_features=None)


def test_constructor_extra_feats():
    model_extra_feats = FeedForward(len(poisson_problem.input_variables)+1,len(poisson_problem.output_variables))
    PINN(problem = poisson_problem, model=model_extra_feats, extra_features=extra_feats)

def test_train_cpu():
    poisson_problem = Poisson()
    boundaries = ['gamma1', 'gamma2', 'gamma3', 'gamma4']
    n = 10
    poisson_problem.discretise_domain(n, 'grid', locations=boundaries)
    poisson_problem.discretise_domain(n, 'grid', locations=['D'])
    pinn = PINN(problem = poisson_problem, model=model, extra_features=None, loss=LpLoss())
    trainer = Trainer(solver=pinn, kwargs={'max_epochs' : 5, 'accelerator':'cpu'})
    trainer.train()

def test_train_extra_feats_cpu():
    poisson_problem = Poisson()
    boundaries = ['gamma1', 'gamma2', 'gamma3', 'gamma4']
    n = 10
    poisson_problem.discretise_domain(n, 'grid', locations=boundaries)
    poisson_problem.discretise_domain(n, 'grid', locations=['D'])
    pinn = PINN(problem = poisson_problem, model=model_extra_feats, extra_features=extra_feats)
    trainer = Trainer(solver=pinn, kwargs={'max_epochs' : 5, 'accelerator':'cpu'})
    trainer.train()
"""
def test_train_gpu(): #TODO fix ASAP
    poisson_problem = Poisson()
    boundaries = ['gamma1', 'gamma2', 'gamma3', 'gamma4']
    n = 10
    poisson_problem.discretise_domain(n, 'grid', locations=boundaries)
    poisson_problem.discretise_domain(n, 'grid', locations=['D'])
    poisson_problem.conditions.pop('data') # The input/output pts are allocated on cpu
    pinn = PINN(problem = poisson_problem, model=model, extra_features=None, loss=LpLoss())
    trainer = Trainer(solver=pinn, kwargs={'max_epochs' : 5, 'accelerator':'gpu'})
    trainer.train()

def test_train_2():
    boundaries = ['gamma1', 'gamma2', 'gamma3', 'gamma4']
    n = 10
    expected_keys = [[], list(range(0, 50, 3))]
    param = [0, 3]
    for i, truth_key in zip(param, expected_keys):
        pinn = PINN(problem, model)
        pinn.discretise_domain(n, 'grid', locations=boundaries)
        pinn.discretise_domain(n, 'grid', locations=['D'])
        pinn.train(50, save_loss=i)
        assert list(pinn.history_loss.keys()) == truth_key


def test_train_extra_feats():
    pinn = PINN(problem, model_extra_feat, [myFeature()])
    boundaries = ['gamma1', 'gamma2', 'gamma3', 'gamma4']
    n = 10
    pinn.discretise_domain(n, 'grid', locations=boundaries)
    pinn.discretise_domain(n, 'grid', locations=['D'])
    pinn.train(5)


def test_train_2_extra_feats():
    boundaries = ['gamma1', 'gamma2', 'gamma3', 'gamma4']
    n = 10
    expected_keys = [[], list(range(0, 50, 3))]
    param = [0, 3]
    for i, truth_key in zip(param, expected_keys):
        pinn = PINN(problem, model_extra_feat, [myFeature()])
        pinn.discretise_domain(n, 'grid', locations=boundaries)
        pinn.discretise_domain(n, 'grid', locations=['D'])
        pinn.train(50, save_loss=i)
        assert list(pinn.history_loss.keys()) == truth_key


def test_train_with_optimizer_kwargs():
    boundaries = ['gamma1', 'gamma2', 'gamma3', 'gamma4']
    n = 10
    expected_keys = [[], list(range(0, 50, 3))]
    param = [0, 3]
    for i, truth_key in zip(param, expected_keys):
        pinn = PINN(problem, model, optimizer_kwargs={'lr' : 0.3})
        pinn.discretise_domain(n, 'grid', locations=boundaries)
        pinn.discretise_domain(n, 'grid', locations=['D'])
        pinn.train(50, save_loss=i)
        assert list(pinn.history_loss.keys()) == truth_key


def test_train_with_lr_scheduler():
    boundaries = ['gamma1', 'gamma2', 'gamma3', 'gamma4']
    n = 10
    expected_keys = [[], list(range(0, 50, 3))]
    param = [0, 3]
    for i, truth_key in zip(param, expected_keys):
        pinn = PINN(
            problem,
            model,
            lr_scheduler_type=torch.optim.lr_scheduler.CyclicLR,
            lr_scheduler_kwargs={'base_lr' : 0.1, 'max_lr' : 0.3, 'cycle_momentum': False}
        )
        pinn.discretise_domain(n, 'grid', locations=boundaries)
        pinn.discretise_domain(n, 'grid', locations=['D'])
        pinn.train(50, save_loss=i)
        assert list(pinn.history_loss.keys()) == truth_key


# def test_train_batch():
#     pinn = PINN(problem, model, batch_size=6)
#     boundaries = ['gamma1', 'gamma2', 'gamma3', 'gamma4']
#     n = 10
#     pinn.discretise_domain(n, 'grid', locations=boundaries)
#     pinn.discretise_domain(n, 'grid', locations=['D'])
#     pinn.train(5)


# def test_train_batch_2():
#     boundaries = ['gamma1', 'gamma2', 'gamma3', 'gamma4']
#     n = 10
#     expected_keys = [[], list(range(0, 50, 3))]
#     param = [0, 3]
#     for i, truth_key in zip(param, expected_keys):
#         pinn = PINN(problem, model, batch_size=6)
#         pinn.discretise_domain(n, 'grid', locations=boundaries)
#         pinn.discretise_domain(n, 'grid', locations=['D'])
#         pinn.train(50, save_loss=i)
#         assert list(pinn.history_loss.keys()) == truth_key


if torch.cuda.is_available():

    # def test_gpu_train():
    #     pinn = PINN(problem, model, batch_size=20, device='cuda')
    #     boundaries = ['gamma1', 'gamma2', 'gamma3', 'gamma4']
    #     n = 100
    #     pinn.discretise_domain(n, 'grid', locations=boundaries)
    #     pinn.discretise_domain(n, 'grid', locations=['D'])
    #     pinn.train(5)

    def test_gpu_train_nobatch():
        pinn = PINN(problem, model, batch_size=None, device='cuda')
        boundaries = ['gamma1', 'gamma2', 'gamma3', 'gamma4']
        n = 100
        pinn.discretise_domain(n, 'grid', locations=boundaries)
        pinn.discretise_domain(n, 'grid', locations=['D'])
        pinn.train(5)
"""