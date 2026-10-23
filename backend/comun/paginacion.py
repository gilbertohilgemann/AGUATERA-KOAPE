from rest_framework.pagination import PageNumberPagination


class PaginacionEstandar(PageNumberPagination):
    page_size_query_param = 'tamanio'
    max_page_size = 200
    page_query_param = 'pagina'
