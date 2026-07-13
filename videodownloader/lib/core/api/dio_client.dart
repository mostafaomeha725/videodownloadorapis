import 'package:dio/dio.dart';

class DioClient {
  final Dio dio;

  DioClient()
    : dio = Dio(
        BaseOptions(
          baseUrl: 'http://localhost:8000',
          connectTimeout: const Duration(seconds: 10),
          receiveTimeout: const Duration(seconds: 10),
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
          },
        ),
      ) {
    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) {
          // Add custom logic before request is sent
          return handler.next(options);
        },
        onResponse: (response, handler) {
          // Add custom logic for responses
          return handler.next(response);
        },
        onError: (DioException e, handler) {
          // Add custom logic for errors
          return handler.next(e);
        },
      ),
    );
  }
}
