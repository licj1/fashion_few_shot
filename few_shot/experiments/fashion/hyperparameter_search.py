import itertools

import numpy as np
import pandas as pd
import skopt
import tensorflow as tf

from few_shot.experiments.fashion import config
from few_shot.experiments.fashion import evaluate_fashion_few_shot
from few_shot.dataset.fashion import fashion_dfs
from few_shot.dataset.image_pipeline import augmented_img_pipeline_fn
from few_shot.model import build_embedding_model


MAX_SHOTS = 5


def few_shot_optimize(train_df,
                      val_df,
                      test_df,
                      n_shot,
                      k_way_test,
                      k_way_train=config.K_WAY_TRAIN,
                      n_queries_train=config.N_QUERIES_TRAIN,
                      n_queries_test=config.N_QUERIES_TEST,
                      eps_per_epoch=config.EPS_PER_EPOCH,
                      n_epochs=config.N_EPOCHS,
                      test_eps=config.TEST_EPS,
                      img_shape=config.IMG_SHAPE):

    experiment_val_classes = set(np.random.choice(train_df.class_name.unique(), size=16, replace=False))
    experiment_train_df = train_df[~train_df.class_name.isin(experiment_val_classes)]
    experiment_val_df = train_df[train_df.class_name.isin(experiment_val_classes)]

    dimensions = [
        skopt.space.Categorical(name='optimizer_type', categories=('adam', 'rmsprop')),
        skopt.space.Real(name='learning_rate', low=1e-3, high=3),
        skopt.space.Categorical(name='k_way_train_type', categories=('large', 'same')),
        skopt.space.Integer(name='n_convs', low=4, high=6),
        skopt.space.Real(name='dropout', low=0.0, high=0.2),
        skopt.space.Integer(name='early_stop_patience', low=1, high=5)
        ]

    @skopt.utils.use_named_args(dimensions)
    def evaluate_parameters(optimizer_type, learning_rate, k_way_train_type, n_convs, dropout, early_stop_patience):
        print(optimizer_type, learning_rate, k_way_train_type, n_convs, dropout, early_stop_patience)
        if optimizer_type == 'adam':
            optimizer = tf.keras.optimizers.Adam(lr=learning_rate)
        elif optimizer_type == 'rmsprop':
            optimizer = tf.keras.optimizers.RMSprop(lr=learning_rate)
        else:
            raise ValueError('Unsupported optimizer_type')

        if k_way_train_type == 'large':
            cur_k_train = k_way_train
        elif k_way_train_type == 'same':
            cur_k_train = k_way_test
        else:
            raise ValueError('Unsupported k value')
        img_fn = augmented_img_pipeline_fn

        result = evaluate_fashion_few_shot(train_df=experiment_train_df, val_df=experiment_val_df, test_df=val_df,
                                           n_shot=n_shot, k_way_test=k_way_test, k_way_train=cur_k_train,
                                           n_queries_train=n_queries_train, n_queries_test=n_queries_test,
                                           lr=learning_rate, eps_per_epoch=eps_per_epoch, n_epochs=n_epochs,
                                           test_eps=eps_per_epoch, img_shape=img_shape,
                                           embedding_fn=lambda x: build_embedding_model(x, n_convs, dropout),
                                           img_pipeline_fn=img_fn, opt=optimizer, patience=early_stop_patience)
        result['optimizer'] = optimizer_type

        return result['test_loss']

    res = skopt.gp_minimize(evaluate_parameters, dimensions, n_calls=10, n_random_starts=5)

    best_opt, best_lr, best_k_way_type, best_convs, best_dropout, best_patience = res.x

    print(res.x)

    if best_opt == 'adam':
        opt = tf.keras.optimizers.Adam(lr=best_lr)
    elif best_opt == 'rmsprop':
        opt = tf.keras.optimizers.RMSprop(lr=best_lr)
    else:
        raise ValueError('oops')

    result = evaluate_fashion_few_shot(train_df=train_df, val_df=val_df, test_df=test_df, n_shot=n_shots,
                                       k_way_test=k_way_test,
                                       k_way_train=k_way_train if best_k_way_type == 'large' else k_way_test,
                                       n_queries_train=n_queries_train, n_queries_test=n_queries_test, lr=best_lr,
                                       eps_per_epoch=eps_per_epoch, n_epochs=n_epochs, test_eps=test_eps,
                                       img_shape=img_shape, img_pipeline_fn=augmented_img_pipeline_fn, opt=opt,
                                       patience=best_patience)
    result['opt'] = best_opt

    return result


if __name__ == '__main__':
    np.random.seed(23)
    tf.random.set_random_seed(29)

    SHOTS = [5]
    TEST_K_WAY = [15]

    train_df, val_df, test_df = fashion_dfs()

    results = []
    for n_shots, k_way_test in itertools.product(SHOTS, TEST_K_WAY):
        print(f'Running fashion experiment {n_shots}-shot, {k_way_test} way')
        assert k_way_test <= test_df.class_name.nunique()
        result = few_shot_optimize(train_df=train_df,
                                   val_df=val_df,
                                   test_df=test_df,
                                   n_shot=n_shots,
                                   k_way_test=k_way_test,
                                   k_way_train=25)

        results.append(result)

    df = pd.DataFrame.from_records(results)
    print(df)
    df.to_csv('fashion_hyperparameter_search_results.csv')
