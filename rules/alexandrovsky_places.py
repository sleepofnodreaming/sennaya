
from answer import Answer


QUESTIONED = set()


class TagNames(object):
    """
    All constants naming categories assigned to answers.
    """

    VELIKAN = "Комплекс «Великан Парк»"
    CINEMA = "Кинотеатр"

class Postprocs(object):
    """
    A class embracing methods trying to re-assign some answers to a more precise category.
    """
    @classmethod
    def velikan_postprocessing(self, answer: Answer, hls: set):
        if TagNames.VELIKAN in hls:
            hls.add(TagNames.CINEMA)


POSTPROCESSING_SEQUENCE = [Postprocs.velikan_postprocessing]
