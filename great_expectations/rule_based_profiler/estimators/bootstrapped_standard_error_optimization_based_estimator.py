import random
from typing import List, Optional, Union

import numpy as np
import scipy.stats

from great_expectations.rule_based_profiler.estimators import (
    SingleNumericStatisticCalculator,
)
from great_expectations.rule_based_profiler.util import NP_EPSILON


class BootstrappedStandardErrorOptimizationBasedEstimator:
    """
    This bootstrapped estimator is based on the theory presented in "http://dido.econ.yale.edu/~dwka/pub/p1001.pdf":
    @article{Andrews2000a,
        added-at = {2008-04-25T10:38:44.000+0200},
        author = {Andrews, Donald W. K. and Buchinsky, Moshe},
        biburl = {https://www.bibsonomy.org/bibtex/28e2f0a58cdb95e39659921f989a17bdd/smicha},
        day = 01,
        interhash = {778746398daa9ba63bdd95391f1efd37},
        intrahash = {8e2f0a58cdb95e39659921f989a17bdd},
        journal = {Econometrica},
        keywords = {imported},
        month = Jan,
        note = {doi: 10.1111/1468-0262.00092},
        number = 1,
        pages = {23--51},
        timestamp = {2008-04-25T10:38:52.000+0200},
        title = {A Three-step Method for Choosing the Number of Bootstrap Repetitions},
        url = {http://www.blackwell-synergy.com/doi/abs/10.1111/1468-0262.00092},
        volume = 68,
        year = 2000
    }
    The article outlines a three-step minimax procedure that relies on the Central Limit Theorem (C.L.T.) along with the
    bootsrap sampling technique (please see https://en.wikipedia.org/wiki/Bootstrapping_(statistics) for background) for
    computing the stopping criterion, expressed as the optimal number of bootstrap samples, needed to achieve a maximum
    probability that the value of the statistic of interest will be minimally deviating from its actual (ideal) value.

    The paper provides existence and convergence proof of the three-step algorithm for a variety of figures of merit
    (e.g., standard error, confidence intervals, and others).  The present implementation focuses on optimizing the
    standard error measure.  For example, if the statistic_calculator (see below) returns the mean of the sample of a
    distribution as its numeric statistic, then the algorithm will compute the number of bootstrap samples that is
    optimal (i.e., neither too small nor too large) for ensuring that the probability of the event that the deviation of
    this quantity (i.e., the mean) from its actual (ideal, or theoretical) value is fractionally within a (configurable)
    bound close to unity (the parameter controlling how close this probability should be to unity is also configurable).

    The essence of the technique assumes that the bootstrapped samples of the distribution are identically distributed,
    and uses the C.L.T. and the characteristics of the Normal distribution (please refer to
    https://en.wikipedia.org/wiki/Normal_distribution and the links and references therein for background) to relate
    the number of bootstrapped samples to the required quantile, while the variance of the Normal distribution is shown
    theoretically to be equal to the excess kurtosis of the Normal distribution function.  Consequently, in the first
    step, the variance is set to correspond to the excess kurtosis of zero to obtain the initial number of bootstrapped
    samples required.  In the second step, this number is used to generate the bootstrap samples.  In the third step,
    these samples are used to compute the updated excess kurtosis value, thereby yielding the final (optimum) number of
    the bootstrap samples.  For extra assurance, the code below iterates between steps two and three until the maximum
    of all intermediate numbers of bootstrap samples does not change between the successive iterations of the algorithm.

    The public method of this class, "compute_bootstrapped_statistic_samples()",  determines the optimal number of
    bootstrap samples (given the configured tolerances, initialized in the constructor) and returns them to the caller.
    """

    def __init__(
        self,
        statistic_calculator: SingleNumericStatisticCalculator,
        sample_size: int,
        bootstrapped_statistic_deviation_bound: Optional[float] = 1.0e-1,
        prob_bootstrapped_statistic_deviation_outside_bound: Optional[float] = 5.0e-2,
    ):
        """
        # TODO: <Alex>ALEX -- Docstring</Alex>
        """
        self._statistic_calculator = statistic_calculator
        if sample_size < 2:
            raise ValueError(
                f"""Argument "sample_size" in {self.__class__.__name__} must be an integer greater than 1 \
(the value {sample_size} was encountered).
"""
            )
        self._sample_size = sample_size

        self._bootstrapped_statistic_deviation_bound = (
            bootstrapped_statistic_deviation_bound
        )
        self._prob_bootstrapped_statistic_deviation_outside_bound = (
            prob_bootstrapped_statistic_deviation_outside_bound
        )

        self._optimal_num_bootstrap_samples_estimations = []

    def compute_bootstrapped_statistic_samples(self) -> np.ndarray:
        optimal_num_bootstrap_samples: int = (
            self._estimate_optimal_num_bootstrap_samples()
        )
        bootstrap_samples: np.ndarray = self._generate_bootstrap_samples(
            num_bootstrap_samples=optimal_num_bootstrap_samples
        )
        return bootstrap_samples

    def _estimate_optimal_num_bootstrap_samples(
        self,
    ) -> int:
        optimal_num_bootstrap_samples: int = self._estimate_min_num_bootstrap_samples(
            bootstrap_samples=None
        )
        self._optimal_num_bootstrap_samples_estimations.append(
            optimal_num_bootstrap_samples
        )

        previous_max_optimal_num_bootstrap_samples: int = 0
        current_max_optimal_num_bootstrap_samples: int = max(
            self._optimal_num_bootstrap_samples_estimations
        )

        while (
            current_max_optimal_num_bootstrap_samples
            > previous_max_optimal_num_bootstrap_samples
        ):
            bootstrap_samples = self._generate_bootstrap_samples(
                num_bootstrap_samples=optimal_num_bootstrap_samples
            )
            optimal_num_bootstrap_samples = self._estimate_min_num_bootstrap_samples(
                bootstrap_samples=bootstrap_samples
            )
            self._optimal_num_bootstrap_samples_estimations.append(
                optimal_num_bootstrap_samples
            )
            previous_max_optimal_num_bootstrap_samples = (
                current_max_optimal_num_bootstrap_samples
            )
            current_max_optimal_num_bootstrap_samples = max(
                self._optimal_num_bootstrap_samples_estimations
            )

        return current_max_optimal_num_bootstrap_samples

    def _generate_bootstrap_samples(self, num_bootstrap_samples: int) -> np.ndarray:
        idx: int
        # noinspection PyUnusedLocal
        bootstrap_samples: Union[
            np.ndarray,
            List[Union[float, np.float32, np.float64]],
        ] = [
            self._compute_statistic_for_random_sample()
            for idx in range(num_bootstrap_samples)
        ]
        bootstrap_samples = np.array(bootstrap_samples, dtype=np.float64)
        return bootstrap_samples

    def _estimate_min_num_bootstrap_samples(
        self, bootstrap_samples: Optional[np.ndarray] = None
    ) -> int:
        quantile_complement_prob_outside_bound_divided_by_2: np.float64 = (
            scipy.stats.norm.ppf(
                1.0 - self._prob_bootstrapped_statistic_deviation_outside_bound / 2.0
            )
        )

        excess_kurtosis: Optional[np.float64]
        if bootstrap_samples is None:
            excess_kurtosis = np.float64(0.0)
        else:
            excess_kurtosis = self._bootstrapped_sample_excess_kurtosis(
                bootstrap_samples=bootstrap_samples
            )
            excess_kurtosis = max(excess_kurtosis, np.float64(0.0))

        statistic_deviation_standard_variance: np.float64 = (
            self._bootstrapped_statistic_deviation_standard_variance(
                excess_kurtosis=excess_kurtosis
            )
        )

        bootstrap_samples_fractional: np.float64 = np.float64(
            quantile_complement_prob_outside_bound_divided_by_2
            * statistic_deviation_standard_variance
            / (
                self._bootstrapped_statistic_deviation_bound
                * self._bootstrapped_statistic_deviation_bound
            )
        )
        bootstrap_samples: int = round(bootstrap_samples_fractional)

        return bootstrap_samples

    def _generate_random_sample_indexes(
        self,
    ) -> List[int]:
        permutation: List[int] = np.arange(self._sample_size)
        return random.choices(permutation, k=self._sample_size)

    def _compute_statistic_for_random_sample(self) -> np.float64:
        random_sample_indexes: List[int] = self._generate_random_sample_indexes()
        original_data_sample_ids: List[
            Union[
                bytes,
                str,
                int,
                float,
                complex,
                tuple,
                frozenset,
            ]
        ] = self._statistic_calculator.data_point_identifiers
        idx: int
        randomized_data_point_identifiers: List[
            Union[
                bytes,
                str,
                int,
                float,
                complex,
                tuple,
                frozenset,
            ]
        ] = [original_data_sample_ids[idx] for idx in random_sample_indexes]
        computed_sample_statistic: np.float64 = (
            self._statistic_calculator.compute_numeric_statistic(
                randomized_data_point_identifiers=randomized_data_point_identifiers
            )
        )
        return computed_sample_statistic

    @staticmethod
    def _bootstrapped_statistic_deviation_standard_variance(
        excess_kurtosis: Optional[np.float64] = 0.0,
    ) -> np.float64:
        return np.float64((2.0 + excess_kurtosis) / 4.0)

    def _bootstrapped_sample_excess_kurtosis(
        self,
        bootstrap_samples: np.ndarray,
    ) -> np.float64:
        return np.float64(
            self._bootstrapped_sample_kurtosis(bootstrap_samples=bootstrap_samples)
            - 3.0
        )

    def _bootstrapped_sample_kurtosis(
        self,
        bootstrap_samples: np.ndarray,
    ) -> np.float64:
        num_bootstrap_samples: int = bootstrap_samples.size
        if num_bootstrap_samples < 2:
            raise ValueError(
                f"""Number of bootstrap samples in {self.__class__.__name__} must be an integer greater than 1 \
(the value {num_bootstrap_samples} was encountered).
"""
            )
        sample_mean: np.float64 = self._bootstrapped_sample_mean(
            bootstrap_samples=bootstrap_samples
        )
        bootstrap_samples_mean_removed: np.ndarray = bootstrap_samples - sample_mean
        bootstrap_samples_mean_removed_power_4: np.ndarray = np.power(
            bootstrap_samples_mean_removed, 4
        )
        sample_standard_variance: np.float64 = (
            self._bootstrapped_sample_standard_variance_unbiased(
                bootstrap_samples=bootstrap_samples
            )
        )
        sample_kurtosis: np.float64 = np.sum(bootstrap_samples_mean_removed_power_4) / (
            (num_bootstrap_samples - 1)
            * sample_standard_variance
            * sample_standard_variance
        )
        return sample_kurtosis

    def _bootstrapped_sample_standard_variance_unbiased(
        self,
        bootstrap_samples: np.ndarray,
    ) -> np.float64:
        num_bootstrap_samples: int = bootstrap_samples.size
        if num_bootstrap_samples < 2:
            raise ValueError(
                f"""Number of bootstrap samples in {self.__class__.__name__} must be an integer greater than 1 \
(the value {num_bootstrap_samples} was encountered).
"""
            )

        sample_variance: np.float64 = self._bootstrapped_sample_variance_biased(
            bootstrap_samples=bootstrap_samples
        )
        sample_standard_variance: np.float64 = np.float64(
            num_bootstrap_samples * sample_variance / (num_bootstrap_samples - 1)
        )
        return sample_standard_variance

    @staticmethod
    def _bootstrapped_sample_variance_biased(
        bootstrap_samples: np.ndarray,
    ) -> np.float64:
        sample_variance: Union[np.ndarray, np.float64] = (
            np.var(bootstrap_samples) + NP_EPSILON
        )
        return np.float64(sample_variance)

    @staticmethod
    def _bootstrapped_sample_mean(
        bootstrap_samples: np.ndarray,
    ) -> np.float64:
        sample_mean: Union[np.ndarray, np.float64] = np.mean(bootstrap_samples)
        return np.float64(sample_mean)