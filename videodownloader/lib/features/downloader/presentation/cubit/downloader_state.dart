import 'package:equatable/equatable.dart';
import '../../domain/downloader_entity.dart';

abstract class DownloaderState extends Equatable {
  const DownloaderState();

  @override
  List<Object?> get props => [];
}

class DownloaderInitial extends DownloaderState {}

class DownloaderLoading extends DownloaderState {}

class DownloaderSuccess extends DownloaderState {
  final VideoDetails videoDetails;

  const DownloaderSuccess({required this.videoDetails});

  @override
  List<Object?> get props => [videoDetails];
}

class DownloaderError extends DownloaderState {
  final String message;

  const DownloaderError({required this.message});

  @override
  List<Object?> get props => [message];
}
