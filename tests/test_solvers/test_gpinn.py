import torch

from pina.problem import SpatialProblem, InverseProblem
from pina.operators import laplacian
from pina.geometry import CartesianDomain
from pina import Condition, LabelTensor
from pina.solvers import GPINN
from pina.trainer import Trainer
from pina.model import FeedForward
from pina.equation.equation import Equation
from pina.equation.equation_factory import FixedValue
from pina.loss import LpLoss


def laplace_equation(input_, output_):
    force_term = (torch.sin(input_.extract(['x']) * torch.pi) *
                  torch.sin(input_.extract(['y']) * torch.pi))
    delta_u = laplacian(output_.extract(['u']), input_)
    return delta_u - force_term


my_laplace = Equation(laplace_equation)
in_ = LabelTensor(torch.tensor([[0., 1.]]), ['x', 'y'])
out_ = LabelTensor(torch.tensor([[0.]]), ['u'])
in2_ = LabelTensor(torch.rand(60, 2), ['x', 'y'])
out2_ = LabelTensor(torch.rand(60, 1), ['u'])


class InversePoisson(SpatialProblem, InverseProblem):
    '''
    Problem definition for the Poisson equation.
    '''
    output_variables = ['u']
    x_min = -2
    x_max = 2
    y_min = -2
    y_max = 2
    data_input = LabelTensor(torch.rand(10, 2), ['x', 'y'])
    data_output = LabelTensor(torch.rand(10, 1), ['u'])
    spatial_domain = CartesianDomain({'x': [x_min, x_max], 'y': [y_min, y_max]})
    # define the ranges for the parameters
    unknown_parameter_domain = CartesianDomain({'mu1': [-1, 1], 'mu2': [-1, 1]})

    def laplace_equation(input_, output_, params_):
        '''
        Laplace equation with a force term.
        '''
        force_term = torch.exp(
                - 2*(input_.extract(['x']) - params_['mu1'])**2
                - 2*(input_.extract(['y']) - params_['mu2'])**2)
        delta_u = laplacian(output_, input_, components=['u'], d=['x', 'y'])

        return delta_u - force_term

    # define the conditions for the loss (boundary conditions, equation, data)
    conditions = {
        'gamma1': Condition(location=CartesianDomain({'x': [x_min, x_max],
            'y':  y_max}),
            equation=FixedValue(0.0, components=['u'])),
        'gamma2': Condition(location=CartesianDomain(
            {'x': [x_min, x_max], 'y': y_min}),
            equation=FixedValue(0.0, components=['u'])),
        'gamma3': Condition(location=CartesianDomain(
            {'x':  x_max, 'y': [y_min, y_max]}),
            equation=FixedValue(0.0, components=['u'])),
        'gamma4': Condition(location=CartesianDomain(
            {'x': x_min, 'y': [y_min, y_max]
            }),
            equation=FixedValue(0.0, components=['u'])),
        'D': Condition(location=CartesianDomain(
            {'x': [x_min, x_max], 'y': [y_min, y_max]
            }),
        equation=Equation(laplace_equation)),
        'data': Condition(
            input_points=data_input.extract(['x', 'y']),
            output_points=data_output)
    }


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
            input_points=LabelTensor(torch.rand(size=(100, 2)), ['x', 'y']),
            equation=my_laplace),
        'data': Condition(
            input_points=in_,
            output_points=out_),
        'data2': Condition(
            input_points=in2_,
            output_points=out2_)
    }

    def poisson_sol(self, pts):
        return -(torch.sin(pts.extract(['x']) * torch.pi) *
                 torch.sin(pts.extract(['y']) * torch.pi)) / (2 * torch.pi**2)

    truth_solution = poisson_sol


class myFeature(torch.nn.Module):
    """
    Feature: sin(x)
    """

    def __init__(self):
        super(myFeature, self).__init__()

    def forward(self, x):
        t = (torch.sin(x.extract(['x']) * torch.pi) *
             torch.sin(x.extract(['y']) * torch.pi))
        return LabelTensor(t, ['sin(x)sin(y)'])


# make the problem
poisson_problem = Poisson()
model = FeedForward(len(poisson_problem.input_variables),
                    len(poisson_problem.output_variables))
model_extra_feats = FeedForward(
    len(poisson_problem.input_variables) + 1,
    len(poisson_problem.output_variables))
extra_feats = [myFeature()]


def test_constructor():
    GPINN(problem=poisson_problem, model=model, extra_features=None)


def test_constructor_extra_feats():
    model_extra_feats = FeedForward(
        len(poisson_problem.input_variables) + 1,
        len(poisson_problem.output_variables))
    GPINN(problem=poisson_problem,
         model=model_extra_feats,
         extra_features=extra_feats)


def test_train_cpu():
    poisson_problem = Poisson()
    boundaries = ['gamma1', 'gamma2', 'gamma3', 'gamma4']
    n = 10
    poisson_problem.discretise_domain(n, 'grid', locations=boundaries)
    pinn = GPINN(problem = poisson_problem,
                 model=model, extra_features=None, loss=LpLoss())
    trainer = Trainer(solver=pinn, max_epochs=1,
                      accelerator='cpu', batch_size=20)
    trainer.train()

def test_log():
    poisson_problem.discretise_domain(100)
    solver = GPINN(problem = poisson_problem, model=model,
                extra_features=None, loss=LpLoss())
    trainer = Trainer(solver, max_epochs=2, accelerator='cpu')
    trainer.train()
    # assert the logged metrics are correct
    logged_metrics = sorted(list(trainer.logged_metrics.keys()))
    total_metrics = sorted(
        list([key + '_loss' for key in poisson_problem.conditions.keys()])
        + ['mean_loss'])
    assert logged_metrics == total_metrics

def test_train_restore():
    tmpdir = "tests/tmp_restore"
    poisson_problem = Poisson()
    boundaries = ['gamma1', 'gamma2', 'gamma3', 'gamma4']
    n = 10
    poisson_problem.discretise_domain(n, 'grid', locations=boundaries)
    pinn = GPINN(problem=poisson_problem,
                model=model,
                extra_features=None,
                loss=LpLoss())
    trainer = Trainer(solver=pinn,
                      max_epochs=5,
                      accelerator='cpu',
                      default_root_dir=tmpdir)
    trainer.train()
    ntrainer = Trainer(solver=pinn, max_epochs=15, accelerator='cpu')
    t = ntrainer.train(
        ckpt_path=f'{tmpdir}/lightning_logs/version_0/'
        'checkpoints/epoch=4-step=10.ckpt')
    import shutil
    shutil.rmtree(tmpdir)


def test_train_load():
    tmpdir = "tests/tmp_load"
    poisson_problem = Poisson()
    boundaries = ['gamma1', 'gamma2', 'gamma3', 'gamma4']
    n = 10
    poisson_problem.discretise_domain(n, 'grid', locations=boundaries)
    pinn = GPINN(problem=poisson_problem,
                model=model,
                extra_features=None,
                loss=LpLoss())
    trainer = Trainer(solver=pinn,
                      max_epochs=15,
                      accelerator='cpu',
                      default_root_dir=tmpdir)
    trainer.train()
    new_pinn = GPINN.load_from_checkpoint(
        f'{tmpdir}/lightning_logs/version_0/checkpoints/epoch=14-step=30.ckpt',
        problem = poisson_problem, model=model)
    test_pts = CartesianDomain({'x': [0, 1], 'y': [0, 1]}).sample(10)
    assert new_pinn.forward(test_pts).extract(['u']).shape == (10, 1)
    assert new_pinn.forward(test_pts).extract(
        ['u']).shape == pinn.forward(test_pts).extract(['u']).shape
    torch.testing.assert_close(
        new_pinn.forward(test_pts).extract(['u']),
        pinn.forward(test_pts).extract(['u']))
    import shutil
    shutil.rmtree(tmpdir)

def test_train_inverse_problem_cpu():
    poisson_problem = InversePoisson()
    boundaries = ['gamma1', 'gamma2', 'gamma3', 'gamma4', 'D']
    n = 100
    poisson_problem.discretise_domain(n, 'random', locations=boundaries)
    pinn = GPINN(problem = poisson_problem,
                 model=model, extra_features=None, loss=LpLoss())
    trainer = Trainer(solver=pinn, max_epochs=1,
                      accelerator='cpu', batch_size=20)
    trainer.train()


# # TODO does not currently work
# def test_train_inverse_problem_restore():
#     tmpdir = "tests/tmp_restore_inv"
#     poisson_problem = InversePoisson()
#     boundaries = ['gamma1', 'gamma2', 'gamma3', 'gamma4', 'D']
#     n = 100
#     poisson_problem.discretise_domain(n, 'random', locations=boundaries)
#     pinn = GPINN(problem=poisson_problem,
#                 model=model,
#                 extra_features=None,
#                 loss=LpLoss())
#     trainer = Trainer(solver=pinn,
#                       max_epochs=5,
#                       accelerator='cpu',
#                       default_root_dir=tmpdir)
#     trainer.train()
#     ntrainer = Trainer(solver=pinn, max_epochs=5, accelerator='cpu')
#     t = ntrainer.train(
#         ckpt_path=f'{tmpdir}/lightning_logs/version_0/checkpoints/epoch=4-step=10.ckpt')
#     import shutil
#     shutil.rmtree(tmpdir)


def test_train_inverse_problem_load():
    tmpdir = "tests/tmp_load_inv"
    poisson_problem = InversePoisson()
    boundaries = ['gamma1', 'gamma2', 'gamma3', 'gamma4', 'D']
    n = 100
    poisson_problem.discretise_domain(n, 'random', locations=boundaries)
    pinn = GPINN(problem=poisson_problem,
                model=model,
                extra_features=None,
                loss=LpLoss())
    trainer = Trainer(solver=pinn,
                      max_epochs=15,
                      accelerator='cpu',
                      default_root_dir=tmpdir)
    trainer.train()
    new_pinn = GPINN.load_from_checkpoint(
        f'{tmpdir}/lightning_logs/version_0/checkpoints/epoch=14-step=30.ckpt',
        problem = poisson_problem, model=model)
    test_pts = CartesianDomain({'x': [0, 1], 'y': [0, 1]}).sample(10)
    assert new_pinn.forward(test_pts).extract(['u']).shape == (10, 1)
    assert new_pinn.forward(test_pts).extract(
        ['u']).shape == pinn.forward(test_pts).extract(['u']).shape
    torch.testing.assert_close(
        new_pinn.forward(test_pts).extract(['u']),
        pinn.forward(test_pts).extract(['u']))
    import shutil
    shutil.rmtree(tmpdir)

# # TODO fix asap. Basically sampling few variables
# # works only if both variables are in a range.
# # if one is fixed and the other not, this will
# # not work. This test also needs to be fixed and
# # insert in test problem not in test pinn.
# def test_train_cpu_sampling_few_vars():
#     poisson_problem = Poisson()
#     boundaries = ['gamma1', 'gamma2', 'gamma3']
#     n = 10
#     poisson_problem.discretise_domain(n, 'grid', locations=boundaries)
#     poisson_problem.discretise_domain(n, 'random', locations=['gamma4'], variables=['x'])
#     poisson_problem.discretise_domain(n, 'random', locations=['gamma4'], variables=['y'])
#     pinn = GPINN(problem = poisson_problem, model=model, extra_features=None, loss=LpLoss())
#     trainer = Trainer(solver=pinn, kwargs={'max_epochs' : 5, 'accelerator':'cpu'})
#     trainer.train()


def test_train_extra_feats_cpu():
    poisson_problem = Poisson()
    boundaries = ['gamma1', 'gamma2', 'gamma3', 'gamma4']
    n = 10
    poisson_problem.discretise_domain(n, 'grid', locations=boundaries)
    pinn = GPINN(problem=poisson_problem,
                model=model_extra_feats,
                extra_features=extra_feats)
    trainer = Trainer(solver=pinn, max_epochs=5, accelerator='cpu')
    trainer.train()


# TODO, fix GitHub actions to run also on GPU
# def test_train_gpu():
#     poisson_problem = Poisson()
#     boundaries = ['gamma1', 'gamma2', 'gamma3', 'gamma4']
#     n = 10
#     poisson_problem.discretise_domain(n, 'grid', locations=boundaries)
#     pinn = GPINN(problem = poisson_problem, model=model, extra_features=None, loss=LpLoss())
#     trainer = Trainer(solver=pinn, kwargs={'max_epochs' : 5, 'accelerator':'gpu'})
#     trainer.train()

# def test_train_gpu(): #TODO fix ASAP
#     poisson_problem = Poisson()
#     boundaries = ['gamma1', 'gamma2', 'gamma3', 'gamma4']
#     n = 10
#     poisson_problem.discretise_domain(n, 'grid', locations=boundaries)
#     poisson_problem.conditions.pop('data') # The input/output pts are allocated on cpu
#     pinn = GPINN(problem = poisson_problem, model=model, extra_features=None, loss=LpLoss())
#     trainer = Trainer(solver=pinn, kwargs={'max_epochs' : 5, 'accelerator':'gpu'})
#     trainer.train()

# def test_train_2():
#     boundaries = ['gamma1', 'gamma2', 'gamma3', 'gamma4']
#     n = 10
#     expected_keys = [[], list(range(0, 50, 3))]
#     param = [0, 3]
#     for i, truth_key in zip(param, expected_keys):
#         pinn = GPINN(problem, model)
#         pinn.discretise_domain(n, 'grid', locations=boundaries)
#         pinn.discretise_domain(n, 'grid', locations=['D'])
#         pinn.train(50, save_loss=i)
#         assert list(pinn.history_loss.keys()) == truth_key


# def test_train_extra_feats():
#     pinn = GPINN(problem, model_extra_feat, [myFeature()])
#     boundaries = ['gamma1', 'gamma2', 'gamma3', 'gamma4']
#     n = 10
#     pinn.discretise_domain(n, 'grid', locations=boundaries)
#     pinn.discretise_domain(n, 'grid', locations=['D'])
#     pinn.train(5)


# def test_train_2_extra_feats():
#     boundaries = ['gamma1', 'gamma2', 'gamma3', 'gamma4']
#     n = 10
#     expected_keys = [[], list(range(0, 50, 3))]
#     param = [0, 3]
#     for i, truth_key in zip(param, expected_keys):
#         pinn = GPINN(problem, model_extra_feat, [myFeature()])
#         pinn.discretise_domain(n, 'grid', locations=boundaries)
#         pinn.discretise_domain(n, 'grid', locations=['D'])
#         pinn.train(50, save_loss=i)
#         assert list(pinn.history_loss.keys()) == truth_key


# def test_train_with_optimizer_kwargs():
#     boundaries = ['gamma1', 'gamma2', 'gamma3', 'gamma4']
#     n = 10
#     expected_keys = [[], list(range(0, 50, 3))]
#     param = [0, 3]
#     for i, truth_key in zip(param, expected_keys):
#         pinn = GPINN(problem, model, optimizer_kwargs={'lr' : 0.3})
#         pinn.discretise_domain(n, 'grid', locations=boundaries)
#         pinn.discretise_domain(n, 'grid', locations=['D'])
#         pinn.train(50, save_loss=i)
#         assert list(pinn.history_loss.keys()) == truth_key


# def test_train_with_lr_scheduler():
#     boundaries = ['gamma1', 'gamma2', 'gamma3', 'gamma4']
#     n = 10
#     expected_keys = [[], list(range(0, 50, 3))]
#     param = [0, 3]
#     for i, truth_key in zip(param, expected_keys):
#         pinn = GPINN(
#             problem,
#             model,
#             lr_scheduler_type=torch.optim.lr_scheduler.CyclicLR,
#             lr_scheduler_kwargs={'base_lr' : 0.1, 'max_lr' : 0.3, 'cycle_momentum': False}
#         )
#         pinn.discretise_domain(n, 'grid', locations=boundaries)
#         pinn.discretise_domain(n, 'grid', locations=['D'])
#         pinn.train(50, save_loss=i)
#         assert list(pinn.history_loss.keys()) == truth_key


# # def test_train_batch():
# #     pinn = GPINN(problem, model, batch_size=6)
# #     boundaries = ['gamma1', 'gamma2', 'gamma3', 'gamma4']
# #     n = 10
# #     pinn.discretise_domain(n, 'grid', locations=boundaries)
# #     pinn.discretise_domain(n, 'grid', locations=['D'])
# #     pinn.train(5)


# # def test_train_batch_2():
# #     boundaries = ['gamma1', 'gamma2', 'gamma3', 'gamma4']
# #     n = 10
# #     expected_keys = [[], list(range(0, 50, 3))]
# #     param = [0, 3]
# #     for i, truth_key in zip(param, expected_keys):
# #         pinn = GPINN(problem, model, batch_size=6)
# #         pinn.discretise_domain(n, 'grid', locations=boundaries)
# #         pinn.discretise_domain(n, 'grid', locations=['D'])
# #         pinn.train(50, save_loss=i)
# #         assert list(pinn.history_loss.keys()) == truth_key


# if torch.cuda.is_available():

#     # def test_gpu_train():
#     #     pinn = GPINN(problem, model, batch_size=20, device='cuda')
#     #     boundaries = ['gamma1', 'gamma2', 'gamma3', 'gamma4']
#     #     n = 100
#     #     pinn.discretise_domain(n, 'grid', locations=boundaries)
#     #     pinn.discretise_domain(n, 'grid', locations=['D'])
#     #     pinn.train(5)

#     def test_gpu_train_nobatch():
#         pinn = GPINN(problem, model, batch_size=None, device='cuda')
#         boundaries = ['gamma1', 'gamma2', 'gamma3', 'gamma4']
#         n = 100
#         pinn.discretise_domain(n, 'grid', locations=boundaries)
#         pinn.discretise_domain(n, 'grid', locations=['D'])
#         pinn.train(5)

